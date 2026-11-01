#include "Backend.h"

#include <QCoreApplication>
#include <QDesktopServices>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcessEnvironment>
#include <QStandardPaths>
#include <QUrl>

namespace {
constexpr int kHelloTimeoutMs = 90 * 1000;         // python start + imports; antivirus may scan the venv on first run
constexpr int kLoadStepTimeoutMs = 10 * 60 * 1000; // per model-loading progress step; first CUDA load can be slow
}

Backend::Backend(QObject *parent) : QObject(parent) {
    // GenericDataLocation is %LOCALAPPDATA% on Windows; logs sit next to models and the setup logs.
    m_logDir = QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation) + "/Voxlate/logs";
    m_st["state"] = QVariantMap{{"state", "Starting"}, {"detail", "Starting translation engine…"}};
    m_timer.setSingleShot(true);
    connect(&m_timer, &QTimer::timeout, this, &Backend::onTimeout);
    connect(&m_proc, &QProcess::readyReadStandardOutput, this, &Backend::onReadyRead);
    connect(&m_proc, &QProcess::finished, this, &Backend::onFinished);
    connect(&m_proc, &QProcess::errorOccurred, this, &Backend::onError);
    startWorker();
}

Backend::~Backend() { shutdown(); }

void Backend::setState(const QString &state, const QString &detail) {
    m_st["state"] = QVariantMap{{"state", state}, {"detail", detail}};
    emit changed();
}

// Worker location: <app>/worker/.venv/Scripts/python.exe -m voxlate_worker
// Dev override: VOXLATE_PYTHON and VOXLATE_WORKER_DIR.
void Backend::startWorker() {
    const auto env = QProcessEnvironment::systemEnvironment();
    QString dir = env.value("VOXLATE_WORKER_DIR", QCoreApplication::applicationDirPath() + "/worker");
    QString py = env.value("VOXLATE_PYTHON", dir + "/.venv/Scripts/python.exe");
    m_st.remove("hello");
    if (!QFileInfo::exists(py)) {
        setState("Error", "Translation engine not installed (" + QDir::toNativeSeparators(py) +
                              " is missing). Run \"Voxlate - Repair setup\" from the Start menu.");
        return;
    }
    QDir().mkpath(m_logDir);
    const QString log = m_logDir + "/worker.log";
    QFile::remove(m_logDir + "/worker.prev.log");  // keep the previous run for diagnosis after a Retry
    QFile::rename(log, m_logDir + "/worker.prev.log");
    m_proc.setStandardErrorFile(log);  // never contains transcripts or audio; stdout is the JSON protocol
    m_proc.setWorkingDirectory(dir);
    auto penv = env;
    penv.remove("PYTHONHOME");  // a system Python's settings must not leak into the venv
    penv.remove("PYTHONPATH");
    penv.insert("PYTHONUNBUFFERED", "1");
    penv.insert("PYTHONIOENCODING", "utf-8");
    penv.insert("HF_HUB_OFFLINE", "1");  // models are local folders; never reach the network at runtime
    penv.insert("TRANSFORMERS_OFFLINE", "1");
    penv.insert("HF_HUB_DISABLE_SYMLINKS_WARNING", "1");
    m_proc.setProcessEnvironment(penv);
    m_buf.clear();
    m_proc.start(QDir::toNativeSeparators(py), {"-m", "voxlate_worker"});  // QProcess quotes paths with spaces
    m_timer.start(kHelloTimeoutMs);
    send({{"cmd", "list_devices"}});
    send({{"cmd", "profile_status"}});
}

void Backend::restartWorker() {
    m_timer.stop();
    if (m_proc.state() != QProcess::NotRunning) {
        m_proc.kill();
        m_proc.waitForFinished(2000);
    }
    m_st.remove("models");
    setState("Starting", "Restarting translation engine…");
    startWorker();
}

void Backend::openLogs() {
    QDir().mkpath(m_logDir);
    QDesktopServices::openUrl(QUrl::fromLocalFile(m_logDir));
}

void Backend::send(const QVariantMap &cmd) {
    if (m_proc.state() == QProcess::NotRunning) return;  // writes while Starting are buffered by QProcess
    m_proc.write(QJsonDocument(QJsonObject::fromVariantMap(cmd)).toJson(QJsonDocument::Compact) + "\n");
}

void Backend::onReadyRead() {
    m_buf += m_proc.readAllStandardOutput();
    int nl;
    while ((nl = m_buf.indexOf('\n')) >= 0) {
        const QByteArray line = m_buf.left(nl).trimmed();
        m_buf.remove(0, nl + 1);
        const QVariantMap ev = QJsonDocument::fromJson(line).object().toVariantMap();
        const QString name = ev.value("ev").toString();
        if (name.isEmpty()) continue;
        const auto s = m_st.value("state").toMap().value("state").toString();
        if (name == "hello") {  // process is up: preload models right away, with progress in the status line
            m_timer.start(kLoadStepTimeoutMs);
            if (s == "Starting") m_st["state"] = QVariantMap{{"state", "Starting"}, {"detail", "Loading models…"}};
            send({{"cmd", "load_models"}});
        }
        if (name == "models" && ev.value("status") == "loading") {
            m_timer.start(kLoadStepTimeoutMs);
            if (s == "Starting") m_st["state"] = QVariantMap{{"state", "Starting"}, {"detail", ev.value("detail")}};
        }
        if (name == "models" && ev.value("status") == "ready") {
            m_timer.stop();
            if (s == "Starting" || s == "Error")
                m_st["state"] = QVariantMap{{"state", "Ready"}, {"detail", ""}};
        }
        if (name == "models" && ev.value("status") == "error") {
            m_timer.stop();
            m_st["state"] = QVariantMap{{"state", "Error"}, {"detail", "Models failed to load: " + ev.value("detail").toString()}};
        }
        m_st[name] = ev;
        emit workerEvent(ev);
    }
    emit changed();
}

void Backend::onTimeout() {
    if (m_proc.state() == QProcess::NotRunning) return;
    // The worker keeps running: if it becomes ready later, "models ready" moves the state from Error to Ready.
    if (!m_st.contains("hello"))
        setState("Error", QString("The translation engine did not start within %1 s. %2")
                              .arg(kHelloTimeoutMs / 1000).arg(logTail()));
    else
        setState("Error", QString("Models did not finish loading (no progress for %1 min). %2")
                              .arg(kLoadStepTimeoutMs / 60000).arg(logTail()));
}

void Backend::onError(QProcess::ProcessError error) {
    if (error != QProcess::FailedToStart || m_quitting) return;  // crashes are reported by onFinished
    m_timer.stop();
    setState("Error", "Could not start the translation engine: " + m_proc.errorString() +
                          ". Run \"Voxlate - Repair setup\" from the Start menu.");
}

// Last non-empty line of worker.log, usually the Python exception (e.g. "ModuleNotFoundError: ...").
QString Backend::logTail() const {
    QFile f(m_logDir + "/worker.log");
    if (!f.open(QIODevice::ReadOnly)) return {};
    if (f.size() > 4096) f.seek(f.size() - 4096);
    const QStringList lines = QString::fromUtf8(f.readAll()).split('\n', Qt::SkipEmptyParts);
    for (auto it = lines.crbegin(); it != lines.crend(); ++it)
        if (!it->trimmed().isEmpty()) return "Last log line: " + it->trimmed();
    return {};
}

void Backend::onFinished(int code, QProcess::ExitStatus) {
    if (m_quitting) return;
    m_timer.stop();
    // Worker gone => its audio streams are gone => the cable is silent (fail closed).
    setState("Error", QString("Translation engine stopped unexpectedly (code %1). "
                              "Nothing is being sent to the meeting. %2").arg(code).arg(logTail()));
}

bool Backend::translating() const {
    return m_st.value("state").toMap().value("state").toString() == "Translating";
}

QVariant Backend::setting(const QString &key, const QVariant &def) const { return m_settings.value(key, def); }
void Backend::setSetting(const QString &key, const QVariant &value) { m_settings.setValue(key, value); }

// Exit: stop translation, release devices, end the worker. Kill only if it does not exit in time.
void Backend::shutdown() {
    if (m_quitting) return;
    m_quitting = true;
    m_timer.stop();
    if (m_proc.state() == QProcess::NotRunning) return;
    send({{"cmd", "shutdown"}});
    m_proc.closeWriteChannel();
    if (!m_proc.waitForFinished(5000)) {
        m_proc.kill();
        m_proc.waitForFinished(2000);
    }
}
