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

set_target_properties_obs(stream-shower PROPERTIES FOLDER plugins PREFIX "")
