cmake_minimum_required(VERSION 3.28...3.30)

find_package(Qt6 REQUIRED Widgets Gui)

add_library(stinger-maker MODULE)
add_library(OBS::stinger-maker ALIAS stinger-maker)

target_sources(stinger-maker PRIVATE stinger-maker.cpp)

target_link_libraries(
  stinger-maker
  PRIVATE
    OBS::frontend-api
    OBS::libobs
    Qt::Widgets
    Qt::Gui
)

if(OS_WINDOWS)
  configure_file(cmake/windows/obs-module.rc.in stinger-maker.rc)
  target_sources(stinger-maker PRIVATE stinger-maker.rc)
endif()

set_target_properties_obs(stinger-maker PROPERTIES FOLDER plugins PREFIX "")
