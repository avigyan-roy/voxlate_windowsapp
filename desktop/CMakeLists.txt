cmake_minimum_required(VERSION 3.24)
project(Voxlate VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Qt >= 6.5, MSVC 2022 x64 kit (open-source LGPL modules only: Core, Gui, Qml, Quick, QuickControls2, Widgets)
find_package(Qt6 6.5 REQUIRED COMPONENTS Quick QuickControls2 Widgets)
qt_standard_project_setup(REQUIRES 6.5)
# QTP0004 (Qt 6.8+) is newer than REQUIRES 6.5 covers; set it explicitly to silence the warning.
# Only adds qmldir files for QML in subfolders; loadFromModule("Voxlate", "Main") is unaffected.
if(QT_KNOWN_POLICY_QTP0004)
    qt_policy(SET QTP0004 NEW)
endif()

qt_add_executable(Voxlate WIN32
    src/main.cpp
    src/Backend.cpp
    src/Backend.h
)

qt_add_qml_module(Voxlate
    URI Voxlate
    VERSION 1.0
    QML_FILES qml/Main.qml
)

target_link_libraries(Voxlate PRIVATE Qt6::Quick Qt6::QuickControls2 Qt6::Widgets)
target_compile_definitions(Voxlate PRIVATE UNICODE _UNICODE NOMINMAX)

install(TARGETS Voxlate RUNTIME DESTINATION .)
