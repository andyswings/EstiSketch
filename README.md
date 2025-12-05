# EstiSketch

EstiSketch is an evolving, lightweight tool designed for contractors and designers to quickly sketch building plans and perform preliminary cost estimates. Built with an intuitive interface and essential drawing features, EstiSketch aims to help you lay out walls with precision and get immediate visual feedback on dimensions and alignments.

## Current Features

### Essential Drawing Tools
- **Pointer (V)**: Select walls, corners, or objects. Supports box select, shift-extend, and a rich right-click context menu.
- **Pan (P)**: Smoothly navigate the canvas.
- **Zoom**: Controls for Zoom In (Ctrl+=), Out (Ctrl+-), and Reset (Ctrl+0). Mouse wheel and pinch gestures supported.
- **Undo/Redo**: Full undo history (Ctrl+Z / Ctrl+Y).

### Wall & Room System
- **Draw Walls (W)**: Rendered with high-quality mitered corners. Live snapping to grid/endpoints and real-time measurement labels.
- **Draw Rooms (R)**: Click connection points or double-click a closed loop to auto-generate a room.
- **Advanced Wall Properties**: Edit wall thickness, height, stud spacing, insulation type, fire rating, and finish materials via the **Properties Dock**.
- **Foundations**: Toggle footers on walls and configure their depth/offsets.
- **Smart Joining**:
    - **Join Walls**: Strictly merge selected segments.
    - **Join Connected Walls**: Automatically repair/merge all touching wall chains.

### Openings & Attributes
- **Add Doors (D) & Windows (A)**: Place openings on walls.
- **Context Editing**: Right-click to change door types (Frame, Pocket, French, Sliding, Garage), toggle swing direction, or flip orientation.

### Annotations
- **Add Polyline (L)**: Draw arbitrary shapes or lines for diagrams.

### File Operations & Interoperability
- **Save/Open**: Custom XML project format preserves all properties and relationships.
- **Import Sweet Home 3D**: Import `.sh3d` files to migrate layouts into EstiSketch.

### Estimation & Materials (Planned)
- **Manage Materials (Ctrl+M)**: Configure library of available construction materials.
- **Takeoffs**:
    - **Estimate Materials (Ctrl+Shift+M)**: Generate material lists based on wall properties (studs, insulation, surfaces).
    - **Estimate Cost (Ctrl+Shift+C)**: Calculate preliminary costs.

## Planned Features
- **PDF Export**: Robust export to standard document formats.
- **Custom Heights/Widths**: Support for arbitrary numeric input in properties.


## Installation and Usage

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/andyswings/EstiSketch.git
   cd EstiSketch
   ```

2. **Install Dependencies:**

    Ensure you have Python 3 and GTK4 installed.

    ```bash
    sudo apt install libgirepository-2.0-dev gcc libcairo2-dev pkg-config python3-dev gir1.2-gtk-4.0 python3-pip
    ```


3. **Create and Activate a Virtual Environment**
  
    ```bash
    pip install uv
    uv venv estisketch
    source estisketch/bin/activate
    ```

4. **Install Python Packages in the Venv**

    ```bash
    uv pip install pycairo
    uv pip install PyGObject
    ```

5. **Run the Application:**

    ```bash
    python main.py
    ```

**Contributing**
Contributions are welcome!

Fork the repository, make your changes, and submit a pull request.
For major changes, please open an issue first to discuss your ideas.


**License**
This project is licensed under the MIT License.