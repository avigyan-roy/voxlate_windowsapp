#include <QAction>
#include <QApplication>
#include <QMenu>
#include <QPainter>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickStyle>
#include <QQuickWindow>
#include <QSystemTrayIcon>

#include "Backend.h"

static QIcon makeIcon(const QColor &c) {
    QPixmap pm(64, 64);
    pm.fill(Qt::transparent);
    QPainter p(&pm);
    p.setRenderHint(QPainter::Antialiasing);
    p.setBrush(c);
    p.setPen(Qt::NoPen);
    p.drawEllipse(2, 2, 60, 60);
    p.setPen(Qt::white);
    QFont f("Segoe UI", 30, QFont::Bold);
    p.setFont(f);
    p.drawText(pm.rect(), Qt::AlignCenter, "V");
    return QIcon(pm);
}

int main(int argc, char *argv[]) {
    QApplication app(argc, argv);
    QApplication::setOrganizationName("Voxlate");
    QApplication::setApplicationName("Voxlate");
    QApplication::setQuitOnLastWindowClosed(false);  // X hides to tray; only Exit quits
    QQuickStyle::setStyle("Material");

    const QIcon idleIcon = makeIcon(QColor("#3a4150"));
    const QIcon liveIcon = makeIcon(QColor("#13a89e"));
    app.setWindowIcon(liveIcon);

    Backend backend;
    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty("backend", &backend);
    engine.loadFromModule("Voxlate", "Main");
    if (engine.rootObjects().isEmpty()) return 1;
    auto *win = qobject_cast<QQuickWindow *>(engine.rootObjects().first());

    QSystemTrayIcon tray(idleIcon);
    QMenu menu;
    QAction *open = menu.addAction("Open Voxlate");
    QAction *toggle = menu.addAction("Resume");
    menu.addSeparator();
    QAction *exitAct = menu.addAction("Exit");
    tray.setContextMenu(&menu);
    tray.setToolTip("Voxlate");
    tray.show();

    auto showWin = [win] {
        win->show();
        win->raise();
        win->requestActivate();
    };
    QObject::connect(open, &QAction::triggered, showWin);
    QObject::connect(&tray, &QSystemTrayIcon::activated, [&](QSystemTrayIcon::ActivationReason r) {
        if (r == QSystemTrayIcon::Trigger || r == QSystemTrayIcon::DoubleClick) showWin();
    });
    QObject::connect(toggle, &QAction::triggered, &backend, &Backend::trayToggle);
    QObject::connect(exitAct, &QAction::triggered, [&] {
        backend.shutdown();
        app.quit();
    });
    QObject::connect(&backend, &Backend::changed, [&] {
        const bool on = backend.translating();
        toggle->setText(on ? "Stop translation" : "Resume translation");
        tray.setIcon(on ? liveIcon : idleIcon);
        const auto st = backend.st().value("state").toMap();
        tray.setToolTip("Voxlate · " + st.value("state").toString());
    });
    bool told = false;
    QObject::connect(&backend, &Backend::hiddenToTray, [&] {
        if (told) return;
        told = true;
        tray.showMessage("Voxlate is still running",
                         backend.translating() ? "Translation continues in the background. Use the tray icon to stop or exit."
                                               : "Voxlate is in the tray. Right-click the icon to open or exit.",
                         QSystemTrayIcon::Information, 4000);
    });
    QObject::connect(&app, &QCoreApplication::aboutToQuit, [&] { backend.shutdown(); });
    return app.exec();
}
