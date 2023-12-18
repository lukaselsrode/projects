#!/bin/bash
cd ~/dev_work/projects/total_behavioural_tracker/src/;
rm -rf ./bin/ .buildozer/ ~/.buildozer/;
buildozer android debug;