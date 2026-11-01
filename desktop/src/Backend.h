#pragma once
#include <QObject>
#include <QProcess>
#include <QSettings>
#include <QTimer>
#include <QVariantMap>

// Owns the Python worker process and mirrors its events into one map the QML reads.
// st[<event name>] = latest payload of that event, e.g. st.state.state, st.delay.p50.
class Backend : public QObject {
    Q_OBJECT
    Q_PROPERTY(QVariantMap st READ st NOTIFY changed)
public:
    explicit Backend(QObject *parent = nullptr);
    ~Backend() override;
    QVariantMap st() const { return m_st; }

    Q_INVOKABLE void send(const QVariantMap &cmd);
    Q_INVOKABLE QVariant setting(const QString &key, const QVariant &def = {}) const;
    Q_INVOKABLE void setSetting(const QString &key, const QVariant &value);
    Q_INVOKABLE void restartWorker();
    Q_INVOKABLE void openLogs();
    Q_INVOKABLE QString logDir() const { return m_logDir; }
    Q_INVOKABLE void notifyHidden() { emit hiddenToTray(); }
    Q_INVOKABLE void requestTrayToggle() { emit trayToggle(); }

    bool translating() const;
    void shutdown();

signals:
    void changed();
    void workerEvent(const QVariantMap &ev);
    void hiddenToTray();
    void trayToggle();

private:
    void startWorker();
    void onReadyRead();
    void onFinished(int code, QProcess::ExitStatus status);
    void onError(QProcess::ProcessError error);
    void onTimeout();
    void setState(const QString &state, const QString &detail);
    QString logTail() const;

    QProcess m_proc;
    QByteArray m_buf;
    QVariantMap m_st;
    QSettings m_settings;
    QTimer m_timer;    // readiness watchdog: worker hello, then each model-loading step
    QString m_logDir;  // %LOCALAPPDATA%/Voxlate/logs
    bool m_quitting = false;
};
