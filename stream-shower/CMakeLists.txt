cmake_minimum_required(VERSION 3.28...3.30)

find_package(Qt6 REQUIRED Widgets Network)

add_library(stream-shower MODULE)
add_library(OBS::stream-shower ALIAS stream-shower)

target_sources(stream-shower PRIVATE stream-shower.cpp)

# The Watcher dock uses OBS's own CEF browser widget via the
# browser-panels interface (same API OBS's BrowserDock uses). The
# target only exists after obs-browser is added, so this module is
# registered in plugins/CMakeLists.txt after check_obs_browser().
target_link_libraries(
  stream-shower
  PRIVATE
    OBS::frontend-api
    OBS::libobs
    OBS::browser-panels
    Qt::Widgets
    Qt::Network
)

if(OS_WINDOWS)
  configure_file(cmake/windows/obs-module.rc.in stream-shower.rc)
  target_sources(stream-shower PRIVATE stream-shower.rc)
endif()

# AUTOMOC is REQUIRED, not cosmetic. QCefWidget is declared in
# panel/browser-panel.hpp with Q_OBJECT (titleChanged signal +
# staticMetaObject), but OBS::browser-panels is only an INTERFACE
# library — it ships the header, no compiled moc object. The moc
# for QCefWidget is generated inside whatever target links it and
# has AUTOMOC on: obs-browser does it for itself, and the OBS
# frontend does it for obs-studio.exe (frontend/cmake/ui-qt.cmake).
# Without AUTOMOC here, stream-shower.dll compiles clean but fails
# to link (run 45653951425: LNK2019 QCefWidget::titleChanged +
# LNK2001 QCefWidget::staticMetaObject). With it, CMake mocs the
# INTERFACE-propagated browser-panel.hpp into this DLL, exactly
# the way the frontend's OAuthLogin/BrowserDock get their copy.
# Do not remove this to "simplify" the build, and do not try to
# link obs-browser instead — it is a MODULE (.dll, no import lib).
set_target_properties_obs(stream-shower PROPERTIES FOLDER plugins PREFIX "" AUTOMOC ON)
