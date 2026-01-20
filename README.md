# RepliVision

RepliVision is a 3D food scanning and digital menu system for restaurants. The system allows restaurant staff to quickly scan plated dishes using a custom-built hardware scanner, automatically processes the video into interactive 3D models through photogrammetry, and displays them on a web-based digital menu where customers can view realistic representations of menu items from any angle before ordering. This eliminates uncertainty in food ordering and provides a modern alternative to traditional photography-based menus.

**Demo Video:** See `RepliVisionDemo.mov` for a complete demonstration of the system in action.

**Live Web App:** [https://testrender-9rqt.onrender.com/](https://testrender-9rqt.onrender.com/)

## Repository Contents

This repository contains three main components:

### Scanner (`Scanner.py`)
Raspberry Pi 5 application that controls the hardware scanner. Features dual cameras synchronized with a rotating turntable to capture 360-degree video of food items. Includes LED status indicators and button controls for operation.

### Reconstruction (`Reconstruction/Server.ipynb`)
Google Colab notebook that processes scanner videos into 3D point clouds. Uses the Pi3 for 3D reconstruction and Open3D for cleaning up artifacts. Stores processed PLY files on Google Drive and monitors a command queue for async processing requests.

### Web Application (`Webapp/`)
Flask-based web server with a Three.js 3D viewer frontend. Provides a digital menu interface where customers can browse items, view 3D models, and place orders. Includes manager mode for editing menu items and a kitchen view for order management. All data is stored on Google Drive.

## Quick Start

**Scanner:** Run `python3 Scanner.py` on Raspberry Pi to start the hardware scanner.

**Reconstruction:** Open `Server.ipynb` in Google Colab and run all cells to start processing server.

**Web App:** Install dependencies with `pip install -r requirements.txt` and run `python3 appRender.py` to start the web server.

See the full project documentation in `RepliVision-FinalReport.pdf` for detailed information about the system design, testing, and implementation.

---

Special thanks to the creator of [Pi3](https://github.com/yyfz/Pi3.git) for the photogrammetry library that powers our 3D reconstruction.
