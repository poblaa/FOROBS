# Copilot Instructions for Fuel Consumption Calculator

## Project Overview
This is a web-based GUI application for calculating marine engine fuel consumption. Users plan routes with multiple segments, each specifying RPM, weather conditions, and timing. The app computes fuel usage and remaining onboard fuel (ROB) for voyage planning.

## Core Architecture
- **Frontend**: Browser-based single-page application with map interface
- **Data Flow**: Route segments → Consumption calculations → Cumulative ROB display
- **Offline Capability**: Runs locally in browser without server dependency

## Key Components
- **Map Interface**: Interactive map for route creation (points → segments) using geographic coordinates to calculate real distances
- **Route Planner**: Left panel with segment inputs (distance, RPM, weather, time/speed)
- **Fuel Calculator**: Implements specific consumption model with weather correction
- **Results Display**: Shows ROB after each segment and final consumption

## Fuel Consumption Model
Use the exact equation: `y = 0.000124176621498486*(x*x) - 0.00391529744030522*x + 0.104802913006673`
- `y`: consumption in metric tonnes per hour (mt/h)
- `x`: engine revolutions per minute (RPM)
- Weather correction: `yc = y * W` where `W` ranges 0.5-1.5
- ROB calculation: `HFO_ROB = HFO_start - yc * T` (cumulative per segment)

## Data Structures
- **Route Segment**: {distance_nm, rpm, weather_factor, time_h, speed_kn}
- **Fuel State**: {start_mt, consumed_mt, rob_mt}
- **Route**: Array of segments with cumulative calculations

## UI Layout
- Main screen: Full map with route visualization
- Left panel: Segment input forms and results table
- Reference screenshots: `MAIN_GUI.png` (main screen), `LEG_GUI.png` (route detail)
- Design: Simple, modern look without waterfalls (cascading elements)

## Units and Conventions
- Fuel: metric tonnes (mt)
- Distance: nautical miles (nm)
- Speed: knots (kn)
- Time: hours (h)
- RPM: revolutions per minute
- Weather factor: dimensionless multiplier (0.5-1.5)

## Development Workflow
- Run locally: Open HTML file in browser or use simple HTTP server
- Test calculations: Verify against manual examples in `instructions`
- Map integration: Use Leaflet or similar for point-and-click route creation
- Validation: Ensure weather factor bounds, positive fuel values

## Implementation Notes
- Prioritize offline functionality - no external APIs required
- Calculate time from distance/speed if not provided
- Display intermediate ROB values for each route segment
- Use placeholder buttons for unimplemented features