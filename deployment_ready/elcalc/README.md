# Fuel Consumption Calculator

A web-based application for calculating marine engine fuel consumption with interactive route planning and consumption analysis.

## Features

- **Interactive Map Route Planning**: Click to add waypoints, automatically calculates distances using real geographic coordinates
- **Multi-Segment Routes**: Create routes with multiple segments, each with custom RPM, weather conditions, and timing
- **Real-time Fuel Calculations**: Dynamic calculation of fuel consumption and remaining fuel (ROB)
- **Weather Factor Adjustment**: Adjust consumption based on weather conditions (0.9-1.1 factor)
- **Consumption Charts**: 
  - Model consumption chart showing theoretical engine performance
  - Historical data comparison chart
  - Real-time working point visualization
- **Collapsible Segments**: Organize multiple route segments efficiently
- **Offline Capable**: Runs entirely in the browser

## Live Demo

Visit: [Your GitHub Pages URL will be here]

## Usage

1. **Plan Your Route**:
   - Double-click a segment to activate it
   - Click on the map to add waypoints
   - Distances are calculated automatically
   
2. **Configure Segments**:
   - Set RPM (45-123)
   - Adjust weather factor (0.9-1.1)
   - Enter time or speed (auto-calculates the other)

3. **View Results**:
   - See fuel consumption per segment
   - Monitor remaining fuel (HFO ROB)
   - Click "Data Chart" to view performance charts

## Technical Details

- Pure client-side JavaScript (no server required)
- Leaflet.js for mapping
- Chart.js for data visualization
- SheetJS for Excel data import

## Local Development

Simply open `index.html` in a web browser, or run a local server:

```bash
python3 -m http.server 8000
```

Then visit: http://localhost:8000
