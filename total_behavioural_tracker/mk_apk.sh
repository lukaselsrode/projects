#!/bin/bash
cd src/
rm -rf ~/.buildozer; rm -rf .buildozer/ ; rm -rf ./bin/
buildozer -v android debug
