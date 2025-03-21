# EstiSketch

EstiSketch is an evolving, lightweight tool designed for contractors and designers to quickly sketch building plans and perform preliminary cost estimates. Built with an intuitive interface and essential drawing features, EstiSketch aims to help you lay out walls with precision and get immediate visual feedback on dimensions and alignments.

## Current Features

### Drawing Tools
- **Wall Drawing:**  
  The basic wall drawing tool is mostly complete. You can draw walls with live snapping (to endpoints, angles, and grid points) and real‑time measurement labels that display both the wall’s length and its angle. Double click inside of an existing room to automatically draw walls around it.

- **Room Creation:**  
  Manual point-by-point room drawing is now supported, allowing precise control over room shapes.
  Double-click inside a closed wall loop to automatically create a room, streamlining the process of defining enclosed spaces.

- **Pointer Tool:**
  The pointer tool currently supports two methods of selection. 
    1. Selection of single wall segments or room vertices. 
    2. Box selection or clicking and dragging to select multiple items at once.
  Selection can be extended by holding the shift key and selecting additional segments or vertices. 

- **Pan Tool:**  
  The pan tool works as expected, allowing you to smoothly move around your drawing.

- **Zoom Controls:**  
  Zoom in, zoom out, and reset zoom functions are fully implemented, including pinch to zoom on touch devices, giving you flexible control over your view.

- **Snapping and Live Measurement Labels:**  
  Walls snap precisely to key points and angles, and as you draw, live measurement labels display the current segment’s length and angle. These labels stay parallel to the wall and automatically flip for readability when needed.

### User Interface and Settings
- **Customizable Settings:**  
  A dedicated settings dialog lets you adjust many parameters, including default wall dimensions, snapping thresholds, grid spacing, zoom level, and more. Changes are applied immediately to the drawing area.
- **Toolbar and File Operations:**  
  The toolbar provides access to key functions like Save, Open, and Export as PDF. (These operations currently trigger placeholder actions and will be enhanced in future releases.)

## Planned Features

- **Additional Drawing Tools:**  
  Tools for drawing rooms, adding doors and windows, dimension lines, and text annotations are planned.
- **Materials Management & Cost Estimation:**  
  Future updates will include comprehensive tools for managing materials, estimating quantities, and calculating detailed cost estimates.
- **Advanced Editing:**  
  More robust editing options and additional file export formats will be added as the application matures.

## Installation and Usage

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/andyswings/EstiSketch.git
   cd EstiSketch

2. **Install Dependencies:**
Ensure you have Python 3 and GTK4 installed.

3. **Run the Application:**

    ```bash
    python main.py

**Contributing**
Contributions are welcome!

Fork the repository, make your changes, and submit a pull request.
For major changes, please open an issue first to discuss your ideas.


**License**
This project is licensed under the MIT License.