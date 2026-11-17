#!/bin/sh
# Rebuilds ../intro_3d.js (three.js tree-shaken to what the start-up scenes use). Needs: npm i three@0.158.0 esbuild
cd "$(dirname "$0")" && npx esbuild intro3d.js --bundle --minify --format=iife --global-name=NAB3D --target=es2018 --outfile=../intro_3d.js
