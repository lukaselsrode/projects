[app]
title = Total Behavioral Tracker
package.name = TBT
package.domain = org.test
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,csv,yaml
version = 0.1
requirements = python3,kivy,matplotlib,seaborn,pandas,PyYAML
orientation = portrait, landscape
osx.python_version = 3
osx.kivy_version = 2.2.1
# Android specific
fullscreen = 0
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True
p4a.branch = develop
ios.kivy_ios_url = https://github.com/kivy/kivy-ios
ios.kivy_ios_branch = master
ios.ios_deploy_url = https://github.com/phonegap/ios-deploy
ios.ios_deploy_branch = 1.10.0
ios.codesign.allowed = false
[buildozer]
log_level = 2
warn_on_root = 0
