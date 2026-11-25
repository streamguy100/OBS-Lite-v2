cmake_minimum_required(VERSION 3.28...3.30)

find_package(Qt6 REQUIRED Widgets)

add_library(canvas-chatbox MODULE)
add_library(OBS::canvas-chatbox ALIAS canvas-chatbox)

target_sources(canvas-chatbox PRIVATE canvas-chatbox.cpp)

target_link_libraries(
  canvas-chatbox
  PRIVATE
    OBS::frontend-api
    OBS::libobs
    Qt::Widgets
)

if(OS_WINDOWS)
  configure_file(cmake/windows/obs-module.rc.in canvas-chatbox.rc)
  target_sources(canvas-chatbox PRIVATE canvas-chatbox.rc)
endif()

set_target_properties_obs(canvas-chatbox PROPERTIES FOLDER plugins PREFIX "")
