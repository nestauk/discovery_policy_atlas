# Network Visualizer Component

A React component for visualizing network relationships between variables using D3.js.

## Features

- **Interactive Network Visualization**: Drag nodes, zoom, and pan
- **CSV Data Upload**: Upload your own data with the required format
- **Filtering**: Filter by effect size type, location, study type, and URL
- **Node and Edge Details**: Click on nodes and edges to see detailed information
- **Dark/Light Mode**: Toggle between themes
- **Export**: Save visualizations as SVG files

## Required CSV Format

The component expects CSV files with the following columns:

- `Predictor`: The predictor variable
- `Outcome`: The outcome variable  
- `Effect size`: Numeric effect size
- `Standardised effect size`: Numeric standardized effect size
- `Effect size type`: Type of effect size measure
- `Study type`: Type of study
- `Sample size`: Numeric sample size
- `Location`: Study location
- `URL`: Source URL

## Usage

```tsx
import NetworkVisualizer from '@/components/network/NetworkVisualizer'

function MyPage() {
  return (
    <div>
      <NetworkVisualizer />
    </div>
  )
}
```

## Implementation Details

- Built with React, TypeScript, and D3.js
- Uses force-directed layout for node positioning
- Responsive design with Tailwind CSS
- Supports interactive zoom and pan controls
- Color-coded edges based on effect size (blue = negative, yellow = neutral, red = positive)
- Node types: predictor (blue), outcome (green), both (purple)

## Dependencies

- `d3`: For data visualization and force simulation
- `lucide-react`: For icons
- `react`: Core React functionality