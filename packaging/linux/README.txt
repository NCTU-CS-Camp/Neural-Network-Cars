Neural Network Cars - Ubuntu x86_64 client
===========================================

Run
---
Open a terminal in this directory and run:

  ./NeuralNetworkCars

This package contains only the Pygame client. The competition server and its
SQLite database are not included. The client connects to:

  http://192.168.15.1:8000

Local data
----------
Settings, login profile, training records, shop state, and generated tracks
are stored under:

  ~/.local/share/NeuralNetworkCars

If Ubuntu says the file is not executable, run:

  chmod +x NeuralNetworkCars
