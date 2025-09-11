"use client";

import { useState, useEffect, useRef, useCallback } from 'react';
import * as d3 from 'd3';
import { Upload, Download, Sun, Moon, Plus, Minus, RotateCcw, Search, AlertCircle } from 'lucide-react';
import { useAPI } from '@/lib/api';

// D3 Types for force simulation
type D3Node = Node & d3.SimulationNodeDatum;
type D3Link = Link & d3.SimulationLinkDatum<D3Node>;

interface StudyData {
  Predictor: string;
  Outcome: string;
  'Effect size': number;
  'Standardised effect size': number;
  'Effect size type': string;
  'Study type': string;
  'Sample size': number;
  Location: string;
  URL: string;
}

// API CSV item shape returned from backend before numeric coercion
interface NetworkCsvItem {
  Predictor?: string;
  Outcome?: string;
  'Effect size'?: number | string;
  'Standardised effect size'?: number | string;
  'Effect size type'?: string;
  'Study type'?: string;
  'Sample size'?: number | string;
  Location?: string;
  URL?: string;
}

interface Node {
  id: string;
  type: 'predictor' | 'outcome' | 'both';
  connections: number;
}

interface Link {
  source: string | Node;
  target: string | Node;
  studies: StudyData[];
  averageEffect: number;
}

interface NetworkVisualizerProps {
  projectId?: string; // Optional: if provided, loads data from API; otherwise falls back to CSV upload
}

export default function NetworkVisualizer({ projectId }: NetworkVisualizerProps = {}) {
  const [data, setData] = useState<StudyData[]>([]);
  const [fileName, setFileName] = useState('');
  const [darkMode, setDarkMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dataSource, setDataSource] = useState<'api' | 'csv' | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [selectedLink, setSelectedLink] = useState<Link | null>(null);
  const [activeTab, setActiveTab] = useState('attributes');
  const [filters, setFilters] = useState({
    effectSizeType: [] as string[],
    location: [] as string[],
    studyType: [] as string[],
    url: [] as string[]
  });
  const [displayColumns, setDisplayColumns] = useState([
    'Effect size', 'Effect size type', 'Location', 'Sample size', 
    'Standardised effect size', 'Study type', 'URL'
  ]);
  
  const svgRef = useRef<SVGSVGElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { fetchWithAuth } = useAPI();
  const lastLoadedProjectIdRef = useRef<string | null>(null);
  const fetchRef = useRef(fetchWithAuth);
  // Keep a stable ref to fetchWithAuth to avoid re-running effect when hook identity changes
  useEffect(() => {
    fetchRef.current = fetchWithAuth;
  }, [fetchWithAuth]);

  // Load data from API when projectId is provided
  useEffect(() => {
    const loadApiData = async () => {
      if (!projectId) {
        setDataSource('csv');
        return;
      }

      // Avoid redundant loads for the same projectId
      if (lastLoadedProjectIdRef.current === projectId && dataSource === 'api' && data.length > 0) {
        return;
      }

      setLoading(true);
      setError(null);
      setDataSource('api');

      try {
        const networkData = await fetchRef.current(`/api/analysis-projects/${projectId}/network`);
        const csvData = networkData.csv_data || [];
        
        // Transform API data to match CSV format expected by visualization
        const transformedData: StudyData[] = csvData.map((item: NetworkCsvItem) => ({
          Predictor: item.Predictor || '',
          Outcome: item.Outcome || '',
          'Effect size': Number(item['Effect size'] ?? 0),
          'Standardised effect size': Number(item['Standardised effect size'] ?? 0),
          'Effect size type': item['Effect size type'] || 'Document co-occurrence',
          'Study type': item['Study type'] || 'Theme analysis',
          'Sample size': Number(item['Sample size'] ?? 0),
          Location: item.Location || 'Project-wide',
          URL: item.URL || '',
        }));

        setData(transformedData);
        setFileName(`Network Analysis - Project ${projectId}`);
        lastLoadedProjectIdRef.current = projectId;
        
        if (transformedData.length === 0) {
          setError('No network data available for this project. Make sure synthesis has been completed.');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load network data');
      } finally {
        setLoading(false);
      }
    };

    loadApiData();
  }, [projectId, fetchWithAuth, dataSource, data.length]);

  // Helper functions to get node IDs from source/target (which can be string or Node after D3 processing)
  const getNodeId = (node: string | Node): string => {
    return typeof node === 'string' ? node : node.id;
  };

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target?.result as string;
        const rows = text.split('\n').filter(row => row.trim());
        const headers = rows[0].split(',').map(h => h.trim());
        
        const parsedData = rows.slice(1).map(row => {
          const values = row.split(',').map(v => v.trim());
          const obj: Partial<StudyData> = {};
          headers.forEach((header, index) => {
            if (header === 'Effect size' || header === 'Standardised effect size' || header === 'Sample size') {
              (obj as Record<string, number | string>)[header] = parseFloat(values[index]);
            } else {
              (obj as Record<string, number | string>)[header] = values[index];
            }
          });
          return obj as StudyData;
        });
        
        setData(parsedData);
        setFileName(file.name);
      };
      reader.readAsText(file);
    }
  };

  const processNetworkData = useCallback(() => {
    if (data.length === 0) return { nodes: [], links: [] };

    const nodeMap = new Map<string, Node>();
    const linkMap = new Map<string, Link>();

    // Apply filters
    const filteredData = data.filter(d => {
      if (filters.effectSizeType.length > 0 && !filters.effectSizeType.includes(d['Effect size type'])) return false;
      if (filters.location.length > 0 && !filters.location.includes(d.Location)) return false;
      if (filters.studyType.length > 0 && !filters.studyType.includes(d['Study type'])) return false;
      if (filters.url.length > 0 && !filters.url.includes(d.URL)) return false;
      return true;
    });

    filteredData.forEach(d => {
      // Add predictor node
      if (!nodeMap.has(d.Predictor)) {
        nodeMap.set(d.Predictor, { id: d.Predictor, type: 'predictor', connections: 0 });
      }
      
      // Add outcome node
      if (!nodeMap.has(d.Outcome)) {
        nodeMap.set(d.Outcome, { id: d.Outcome, type: 'outcome', connections: 0 });
      }

      // Update node types
      const predNode = nodeMap.get(d.Predictor)!;
      const outNode = nodeMap.get(d.Outcome)!;
      
      // Check if nodes appear as both predictor and outcome
      if (filteredData.some(item => item.Outcome === d.Predictor)) {
        predNode.type = 'both';
      }
      if (filteredData.some(item => item.Predictor === d.Outcome)) {
        outNode.type = 'both';
      }

      // Add link
      const linkId = `${d.Predictor}-${d.Outcome}`;
      if (!linkMap.has(linkId)) {
        linkMap.set(linkId, {
          source: d.Predictor,
          target: d.Outcome,
          studies: [],
          averageEffect: 0
        });
      }
      linkMap.get(linkId)!.studies.push(d);

      // Update connections
      predNode.connections++;
      outNode.connections++;
    });

    // Calculate average effects
    linkMap.forEach(link => {
      link.averageEffect = link.studies.reduce((sum, s) => sum + s['Standardised effect size'], 0) / link.studies.length;
    });

    return {
      nodes: Array.from(nodeMap.values()),
      links: Array.from(linkMap.values())
    };
  }, [data, filters]);

  const drawNetwork = useCallback(() => {
    if (!svgRef.current || data.length === 0) return;

    const { nodes, links } = processNetworkData();
    
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const width = 728;
    const height = 600;

    const g = svg.append("g").attr("class", "zoom-group");

    // Color scales
    const colorScale = d3.scaleLinear<string>()
      .domain([-1, 0, 1])
      .range(["#3646ff", "#facc15", "#dc2626"]);

    const nodeColorMap = {
      predictor: "#4682B4",
      outcome: "#9ACD32",
      both: "#BA55D3"
    };

    // Create force simulation
    const simulation = d3.forceSimulation(nodes as D3Node[])
      .force("link", d3.forceLink(links as D3Link[]).id((d) => (d as D3Node).id).distance(100))
      .force("charge", d3.forceManyBody().strength(-300))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius(50));

    // Draw links
    const link = g.append("g")
      .attr("class", "links-group")
      .selectAll("path")
      .data(links)
      .enter().append("path")
      .attr("class", "link")
      .attr("stroke", d => colorScale(d.averageEffect))
      .attr("stroke-width", d => Math.min(d.studies.length * 2, 10))
      .attr("fill", "none")
      .attr("opacity", 0.8)
      .style("cursor", "pointer")
      .style("transition", "stroke-width 0.2s, opacity 0.2s")
      .on("click", (event, d) => {
        event.stopPropagation();
        setSelectedLink(d);
        setSelectedNode(null);
      })
      .on("mouseover", function() {
        d3.select(this).attr("opacity", 1).attr("stroke-width", function() {
          return parseFloat(d3.select(this).attr("stroke-width")) + 2;
        });
      })
      .on("mouseout", function(event, d) {
        d3.select(this).attr("opacity", 0.8).attr("stroke-width", Math.min(d.studies.length * 2, 10));
      });

    // Draw arrows
    const arrows = g.append("g")
      .attr("class", "arrows-group")
      .selectAll("path")
      .data(links)
      .enter().append("path")
      .attr("class", "arrow")
      .attr("fill", "#666")
      .attr("opacity", 0.9)
      .style("transition", "opacity 0.2s");

    // Draw nodes
    const node = g.selectAll("g.node")
      .data(nodes)
      .enter().append("g")
      .attr("class", "node")
      .call(d3.drag<SVGGElement, D3Node>()
        .on("start", dragstarted)
        .on("drag", dragged)
        .on("end", dragended))
      .on("click", (event, d) => {
        event.stopPropagation();
        setSelectedNode(d);
        setSelectedLink(null);
      });

    node.append("circle")
      .attr("r", 8)
      .attr("fill", d => nodeColorMap[d.type])
      .attr("stroke", "#ffffff")
      .attr("stroke-width", 2)
      .attr("opacity", 1)
      .style("filter", "drop-shadow(0 1px 2px rgba(0,0,0,0.2))")
      .style("transition", "r 0.2s, filter 0.2s, opacity 0.2s")
      .style("cursor", "pointer")
      .on("mouseover", function() {
        d3.select(this).attr("r", 10).style("filter", "drop-shadow(0 2px 4px rgba(0,0,0,0.3))");
      })
      .on("mouseout", function() {
        d3.select(this).attr("r", 8).style("filter", "drop-shadow(0 1px 2px rgba(0,0,0,0.2))");
      });

    // Add labels background
    node.append("rect")
      .attr("x", 10)
      .attr("y", -9)
      .attr("rx", 3)
      .attr("style", "fill: rgba(255, 255, 255, 0.7); opacity: 1; transition: opacity 0.2s;");

    // Add labels
    const labels = node.append("text")
      .attr("dx", 12)
      .attr("dy", ".35em")
      .style("font-size", "12px")
      .style("fill", "#333")
      .style("pointer-events", "none")
      .style("opacity", 1)
      .style("transition", "opacity 0.2s")
      .text(d => d.id);

    // Update label backgrounds size
    labels.each(function() {
      const bbox = (this as SVGTextElement).getBBox();
      const parentNode = this.parentNode as Element;
      d3.select(parentNode).select("rect")
        .attr("width", bbox.width + 4)
        .attr("height", bbox.height + 6);
    });

    // Apply search filter
    if (searchTerm) {
      node.style("opacity", d => 
        d.id.toLowerCase().includes(searchTerm.toLowerCase()) ? 1 : 0.2
      );
      link.style("opacity", (d: D3Link) => 
        getNodeId(d.source).toLowerCase().includes(searchTerm.toLowerCase()) ||
        getNodeId(d.target).toLowerCase().includes(searchTerm.toLowerCase()) ? 0.8 : 0.1
      );
    }

    // Simulation tick
    simulation.on("tick", () => {
      link.attr("d", (d: D3Link) => {
        return `M${(d.source as D3Node).x},${(d.source as D3Node).y}L${(d.target as D3Node).x},${(d.target as D3Node).y}`;
      });

      arrows.attr("d", (d: D3Link) => {
        const source = d.source as D3Node;
        const target = d.target as D3Node;
        const dx = target.x! - source.x!;
        const dy = target.y! - source.y!;
        const dr = Math.sqrt(dx * dx + dy * dy);
        const offsetX = (dx * 20) / dr;
        const offsetY = (dy * 20) / dr;
        const endX = target.x! - offsetX;
        const endY = target.y! - offsetY;
        
        const angle = Math.atan2(dy, dx);
        const arrowLength = 15;
        const arrowAngle = Math.PI / 6;
        
        const x1 = endX - arrowLength * Math.cos(angle - arrowAngle);
        const y1 = endY - arrowLength * Math.sin(angle - arrowAngle);
        const x2 = endX - arrowLength * Math.cos(angle + arrowAngle);
        const y2 = endY - arrowLength * Math.sin(angle + arrowAngle);
        
        return `M${endX},${endY}L${x1},${y1}L${x2},${y2}Z`;
      });

      node.attr("transform", (d: D3Node) => `translate(${d.x},${d.y})`);
    });

    // Zoom functionality
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 10])
      .on("zoom", (event) => {
        g.attr("transform", event.transform);
      });

    svg.call(zoom);

    // Drag functions
    function dragstarted(event: d3.D3DragEvent<SVGGElement, D3Node, d3.SubjectPosition>, d: D3Node) {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      d.fx = d.x;
      d.fy = d.y;
    }

    function dragged(event: d3.D3DragEvent<SVGGElement, D3Node, d3.SubjectPosition>, d: D3Node) {
      d.fx = event.x;
      d.fy = event.y;
    }

    function dragended(event: d3.D3DragEvent<SVGGElement, D3Node, d3.SubjectPosition>, d: D3Node) {
      if (!event.active) simulation.alphaTarget(0);
      d.fx = null;
      d.fy = null;
    }

    // Zoom controls
    d3.select("#zoom-in").on("click", () => {
      svg.transition().call(zoom.scaleBy, 1.3);
    });

    d3.select("#zoom-out").on("click", () => {
      svg.transition().call(zoom.scaleBy, 0.7);
    });

    d3.select("#zoom-reset").on("click", () => {
      svg.transition().call(zoom.transform, d3.zoomIdentity);
    });

  }, [data, searchTerm, processNetworkData]);

  useEffect(() => {
    drawNetwork();
  }, [drawNetwork]);

  const handleSaveImage = () => {
    if (!svgRef.current) return;
    
    const svgElement = svgRef.current;
    const svgData = new XMLSerializer().serializeToString(svgElement);
    const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
    const svgUrl = URL.createObjectURL(svgBlob);
    
    const downloadLink = document.createElement('a');
    downloadLink.href = svgUrl;
    downloadLink.download = 'network-visualization.svg';
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);
    URL.revokeObjectURL(svgUrl);
  };

  const getUniqueValues = (key: keyof StudyData) => {
    return Array.from(new Set(data.map(d => d[key] as string))).sort();
  };

  const toggleFilter = (category: keyof typeof filters, value: string) => {
    setFilters(prev => ({
      ...prev,
      [category]: prev[category].includes(value)
        ? prev[category].filter(v => v !== value)
        : [...prev[category], value]
    }));
  };

  const selectAllFilter = (category: keyof typeof filters) => {
    setFilters(prev => ({
      ...prev,
      [category]: getUniqueValues(category === 'effectSizeType' ? 'Effect size type' : 
                   category === 'studyType' ? 'Study type' : 
                   category === 'location' ? 'Location' : 'URL')
    }));
  };

  const clearAllFilter = (category: keyof typeof filters) => {
    setFilters(prev => ({
      ...prev,
      [category]: []
    }));
  };

  const resetAllSettings = () => {
    setFilters({
      effectSizeType: [],
      location: [],
      studyType: [],
      url: []
    });
    setDisplayColumns([
      'Effect size', 'Effect size type', 'Location', 'Sample size', 
      'Standardised effect size', 'Study type', 'URL'
    ]);
    setSearchTerm('');
    drawNetwork();
  };

  return (
    <div className={`min-h-screen ${darkMode ? 'bg-gray-900 text-gray-100' : 'bg-gray-50 text-gray-800'} transition-colors duration-300`}>
      <div className="flex flex-col w-full max-w-6xl mx-auto p-4">
        {/* Header */}
        <div className="flex flex-wrap justify-between items-center mb-6 gap-4">
          <h1 className="text-2xl font-bold flex items-center">
            <svg className="mr-2" width="36" height="36" viewBox="0 0 64 64">
              <rect width="64" height="64" rx="12" fill="#f0f4f8"/>
              <path d="M25 21L40 24" stroke="#4682B4" strokeWidth="2.5" fill="none"/>
              <path d="M22 24L30 42" stroke="#9370DB" strokeWidth="2.5" fill="none"/>
              <path d="M42 31L35 42" stroke="#3CB371" strokeWidth="2.5" fill="none"/>
              <circle cx="20" cy="18" r="6" fill="#4682B4" stroke="#ffffff" strokeWidth="1.5"/>
              <circle cx="46" cy="26" r="6" fill="#3CB371" stroke="#ffffff" strokeWidth="1.5"/>
              <circle cx="32" cy="48" r="6" fill="#BA55D3" stroke="#ffffff" strokeWidth="1.5"/>
            </svg>
            LitSynth Network Visualiser
          </h1>
          
          <div className="flex flex-wrap gap-3">
            {/* Zoom Controls */}
            <div className="flex rounded-lg overflow-hidden">
              <button 
                id="zoom-in"
                className={`px-3 py-2 transition-colors border-r ${
                  darkMode ? 'bg-gray-800 hover:bg-gray-700 text-gray-100 border-gray-700' : 
                  'bg-white hover:bg-gray-100 text-gray-800 border-gray-200'
                }`}
                title="Zoom In"
              >
                <Plus size={18} />
              </button>
              <button 
                id="zoom-reset"
                className={`px-3 py-2 transition-colors border-r ${
                  darkMode ? 'bg-gray-800 hover:bg-gray-700 text-gray-100 border-gray-700' : 
                  'bg-white hover:bg-gray-100 text-gray-800 border-gray-200'
                }`}
                title="Reset Zoom"
              >
                <RotateCcw size={18} />
              </button>
              <button 
                id="zoom-out"
                className={`px-3 py-2 transition-colors ${
                  darkMode ? 'bg-gray-800 hover:bg-gray-700 text-gray-100' : 
                  'bg-white hover:bg-gray-100 text-gray-800'
                }`}
                title="Zoom Out"
              >
                <Minus size={18} />
              </button>
            </div>

            {/* Search */}
            <div className="relative">
              <input
                type="text"
                placeholder="Search nodes..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className={`w-64 px-4 py-2 rounded-lg transition-colors shadow-sm ${
                  darkMode ? 'bg-gray-800 text-gray-100 placeholder-gray-400 border border-gray-700' : 
                  'bg-white text-gray-800 placeholder-gray-500 border border-gray-200'
                } focus:outline-none focus:ring-2 focus:ring-blue-500`}
              />
              <Search className="absolute right-3 top-2.5 text-gray-400" size={18} />
            </div>

            {/* Upload CSV - only show when not using API */}
            {dataSource !== 'api' && (
              <label className={`px-4 py-2 rounded-lg flex items-center transition-colors shadow-sm cursor-pointer ${
                darkMode ? 'bg-gray-800 text-gray-100 hover:bg-gray-700 border border-gray-700' : 
                'bg-white text-gray-800 hover:bg-gray-100 border border-gray-200'
              }`}>
                <Upload size={18} className="mr-2" />
                <span>Upload CSV</span>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv"
                  className="hidden"
                  onChange={handleFileUpload}
                />
              </label>
            )}

            {/* Loading indicator for API data */}
            {dataSource === 'api' && loading && (
              <div className={`px-4 py-2 rounded-lg flex items-center transition-colors shadow-sm ${
                darkMode ? 'bg-gray-800 text-gray-100 border border-gray-700' : 
                'bg-white text-gray-800 border border-gray-200'
              }`}>
                <div className="animate-spin h-4 w-4 border-2 border-blue-500 border-t-transparent rounded-full mr-2"></div>
                <span>Loading network data...</span>
              </div>
            )}

            {/* Error indicator for API data */}
            {dataSource === 'api' && error && (
              <div className={`px-4 py-2 rounded-lg flex items-center transition-colors shadow-sm ${
                darkMode ? 'bg-red-900 text-red-100 border border-red-700' : 
                'bg-red-50 text-red-800 border border-red-200'
              }`}>
                <AlertCircle size={18} className="mr-2" />
                <span>Failed to load</span>
              </div>
            )}

            {/* Save Image */}
            <button 
              onClick={handleSaveImage}
              className={`px-4 py-2 rounded-lg flex items-center transition-colors shadow-sm ${
                darkMode ? 'bg-gray-800 text-gray-100 hover:bg-gray-700 border border-gray-700' : 
                'bg-white text-gray-800 hover:bg-gray-100 border border-gray-200'
              }`}
            >
              <Download size={18} className="mr-2" />
              <span>Save Image</span>
            </button>

            {/* Dark Mode Toggle */}
            <button 
              onClick={() => setDarkMode(!darkMode)}
              className={`px-4 py-2 rounded-lg flex items-center transition-colors shadow-sm ${
                darkMode ? 'bg-gray-800 text-gray-100 hover:bg-gray-700 border border-gray-700' : 
                'bg-white text-gray-800 hover:bg-gray-100 border border-gray-200'
              }`}
            >
              {darkMode ? <Sun size={18} className="mr-2" /> : <Moon size={18} className="mr-2" />}
              <span>{darkMode ? 'Light' : 'Dark'} Mode</span>
            </button>
          </div>
        </div>

        {/* Current Dataset Info */}
        {fileName && (
          <div className={`mb-4 p-3 rounded-lg ${darkMode ? 'bg-gray-800 border border-gray-700' : 'bg-white border border-gray-200'}`}>
            <div className="flex items-center">
              <span className="font-medium">Current dataset: </span>
              <span className="ml-2">{fileName}</span>
            </div>
          </div>
        )}

        {/* Main Content */}
        <div className="flex flex-col lg:flex-row gap-6">
          {/* Network Visualization */}
          <div className={`w-full lg:w-8/12 rounded-lg shadow-sm overflow-hidden ${
            darkMode ? 'bg-gray-800 border border-gray-700' : 'bg-white border border-gray-200'
          }`}>
            {data.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-96 text-gray-500">
                <svg className="mb-4" width="100" height="100" viewBox="0 0 64 64">
                  <rect width="64" height="64" rx="12" fill="#e0e7ff"/>
                  <path d="M25 21L40 24" stroke="#4682B4" strokeWidth="2.5" fill="none"/>
                  <path d="M22 24L30 42" stroke="#9370DB" strokeWidth="2.5" fill="none"/>
                  <path d="M42 31L35 42" stroke="#3CB371" strokeWidth="2.5" fill="none"/>
                  <circle cx="20" cy="18" r="6" fill="#4682B4" stroke="#ffffff" strokeWidth="1.5"/>
                  <circle cx="46" cy="26" r="6" fill="#3CB371" stroke="#ffffff" strokeWidth="1.5"/>
                  <circle cx="32" cy="48" r="6" fill="#BA55D3" stroke="#ffffff" strokeWidth="1.5"/>
                </svg>
                {/* API Mode Loading State */}
                {dataSource === 'api' && loading && (
                  <>
                    <div className="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full mb-4"></div>
                    <h2 className="text-xl font-semibold mb-2">Loading Network Data</h2>
                    <p className="text-sm text-center max-w-md">
                      Fetching intervention-result network data from synthesis analysis...
                    </p>
                  </>
                )}

                {/* API Mode Error State */}
                {dataSource === 'api' && error && (
                  <>
                    <AlertCircle size={48} className="mb-4 text-red-500" />
                    <h2 className="text-xl font-semibold mb-2 text-red-600">Failed to Load Network Data</h2>
                    <p className="text-sm text-center max-w-md mb-4 text-red-600">
                      {error}
                    </p>
                    <button 
                      onClick={() => window.location.reload()}
                      className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors"
                    >
                      Retry
                    </button>
                  </>
                )}

                {/* API Mode No Data State */}
                {dataSource === 'api' && !loading && !error && (
                  <>
                    <h2 className="text-xl font-semibold mb-2">No Network Data Available</h2>
                    <p className="text-sm text-center max-w-md">
                      No intervention-result network data found for this project. 
                      Make sure synthesis analysis has been completed.
                    </p>
                  </>
                )}

                {/* CSV Mode Upload State */}
                {dataSource !== 'api' && (
                  <>
                    <h2 className="text-xl font-semibold mb-2">Upload a CSV to visualise your network</h2>
                    <p className="text-sm text-center max-w-md mb-6">
                      Upload a CSV file with the required columns to generate an interactive network visualisation.
                    </p>
                    <div className="text-left">
                      <h3 className="font-semibold mb-2">Required CSV Format</h3>
                      <ul className="list-disc list-inside text-sm space-y-1">
                        <li>Predictor</li>
                        <li>Outcome</li>
                        <li>Effect size</li>
                        <li>Standardised effect size</li>
                        <li>Effect size type</li>
                        <li>Study type</li>
                        <li>Sample size</li>
                        <li>Location</li>
                      </ul>
                    </div>
                    <button 
                      onClick={() => fileInputRef.current?.click()}
                      className="mt-6 px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors flex items-center"
                    >
                      <Upload size={20} className="mr-2" />
                      Upload CSV
                    </button>
                  </>
                )}
              </div>
            ) : (
              <svg 
                ref={svgRef}
                className="w-full h-full"
                width="728"
                height="600"
                viewBox="0 0 728 600"
                style={{ backgroundColor: darkMode ? '#1f2937' : '#ffffff', borderRadius: '8px' }}
              />
            )}
          </div>

          {/* Side Panel */}
          <div className="w-full lg:w-4/12 flex flex-col gap-4">
            {/* Node/Edge Details */}
            <div className={`rounded-lg shadow-sm p-4 ${
              darkMode ? 'bg-gray-800 text-gray-100 border border-gray-700' : 
              'bg-white text-gray-500 border border-gray-200'
            }`}>
              {selectedNode ? (
                <div>
                  <h3 className="text-lg font-semibold mb-3 text-gray-800 dark:text-gray-100">Node Details</h3>
                  <div className="space-y-2">
                    <div>
                      <span className="font-medium">Node:</span> {selectedNode.id}
                    </div>
                    <div>
                      <span className="font-medium">Number of connections:</span> {selectedNode.connections}
                    </div>
                    <div className="mt-4">
                      <h4 className="font-medium mb-2">Incoming Connections</h4>
                      {data.filter(d => d.Outcome === selectedNode.id).length > 0 ? (
                        <div className="text-sm space-y-1">
                          {data.filter(d => d.Outcome === selectedNode.id).map((d, i) => (
                            <div key={i} className="text-gray-600 dark:text-gray-400">
                              ← {d.Predictor}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-gray-500">No incoming connections</p>
                      )}
                    </div>
                    <div className="mt-4">
                      <h4 className="font-medium mb-2">Outgoing Connections</h4>
                      {data.filter(d => d.Predictor === selectedNode.id).length > 0 ? (
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b">
                              <th className="text-left py-1">TO</th>
                              <th className="text-center py-1">STAND. EFFECT SIZE</th>
                              <th className="text-center py-1">STUDIES</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Array.from(new Set(data.filter(d => d.Predictor === selectedNode.id).map(d => d.Outcome))).map(outcome => {
                              const studies = data.filter(d => d.Predictor === selectedNode.id && d.Outcome === outcome);
                              const avgEffect = studies.reduce((sum, s) => sum + s['Standardised effect size'], 0) / studies.length;
                              return (
                                <tr key={outcome} className="border-b">
                                  <td className="py-1">{outcome}</td>
                                  <td className="text-center py-1">{avgEffect.toFixed(2)}</td>
                                  <td className="text-center py-1">{studies.length}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      ) : (
                        <p className="text-sm text-gray-500">No outgoing connections</p>
                      )}
                    </div>
                  </div>
                </div>
              ) : selectedLink ? (
                <div>
                  <h3 className="text-lg font-semibold mb-3 text-gray-800 dark:text-gray-100">Relationship Details</h3>
                  <div className="space-y-2">
                    <div>
                      <span className="font-medium">Predictor:</span> <span className="text-blue-600">{getNodeId(selectedLink.source)}</span>
                    </div>
                    <div>
                      <span className="font-medium">Outcome:</span> <span className="text-green-600">{getNodeId(selectedLink.target)}</span>
                    </div>
                    <div>
                      <span className="font-medium">Stand. Effect Size:</span> {selectedLink.averageEffect?.toFixed(2) || 'N/A'}
                    </div>
                    <div>
                      <span className="font-medium">Studies:</span> {selectedLink.studies?.length || 0}
                    </div>
                    <div className="mt-4">
                      <h4 className="font-medium mb-2">Studies</h4>
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="border-b">
                              <th className="text-left py-1 px-1">STAND. EFFECT SIZE</th>
                              {displayColumns.includes('Effect size') && <th className="text-left py-1 px-1">EFFECT SIZE</th>}
                              {displayColumns.includes('Effect size type') && <th className="text-left py-1 px-1">EFFECT SIZE TYPE</th>}
                              {displayColumns.includes('Location') && <th className="text-left py-1 px-1">LOCATION</th>}
                              {displayColumns.includes('Sample size') && <th className="text-left py-1 px-1">SAMPLE SIZE</th>}
                            </tr>
                          </thead>
                          <tbody>
                            {selectedLink.studies.map((study, i) => (
                              <tr key={i} className="border-b">
                                <td className="py-1 px-1">{study['Standardised effect size'].toFixed(2)}</td>
                                {displayColumns.includes('Effect size') && <td className="py-1 px-1">{study['Effect size'].toFixed(2)}</td>}
                                {displayColumns.includes('Effect size type') && <td className="py-1 px-1">{study['Effect size type']}</td>}
                                {displayColumns.includes('Location') && <td className="py-1 px-1">{study.Location}</td>}
                                {displayColumns.includes('Sample size') && <td className="py-1 px-1">{study['Sample size']}</td>}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                    <div className="mt-4">
                      <h4 className="font-medium mb-2">Effect Size Distribution</h4>
                      <div className="h-24 bg-gray-100 dark:bg-gray-700 rounded flex items-end justify-center space-x-1 p-2">
                        {selectedLink.studies.map((study, i) => {
                          const maxEffect = Math.max(...selectedLink.studies.map(s => Math.abs(s['Standardised effect size'])));
                          const height = (Math.abs(study['Standardised effect size']) / maxEffect) * 100;
                          return (
                            <div
                              key={i}
                              className="flex-1 bg-blue-500 rounded-t"
                              style={{ height: `${height}%` }}
                              title={`Effect: ${study['Standardised effect size'].toFixed(2)}`}
                            />
                          );
                        })}
                      </div>
                      <div className="flex justify-between text-xs mt-1">
                        <span>Mean: {selectedLink.averageEffect.toFixed(2)}</span>
                        <span>Median: {(() => {
                          const sorted = [...selectedLink.studies].sort((a, b) => a['Standardised effect size'] - b['Standardised effect size']);
                          const mid = Math.floor(sorted.length / 2);
                          return sorted.length % 2 ? sorted[mid]['Standardised effect size'].toFixed(2) : 
                            ((sorted[mid - 1]['Standardised effect size'] + sorted[mid]['Standardised effect size']) / 2).toFixed(2);
                        })()}</span>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <p className="text-center py-6">Click on a node or edge to see details</p>
              )}
            </div>

            {/* Legend */}
            <div className={`rounded-lg shadow-sm p-4 ${
              darkMode ? 'bg-gray-800 border border-gray-700' : 'bg-white border border-gray-200'
            }`}>
              <h2 className="text-lg font-medium mb-3">Legend</h2>
              
              <div className="mb-4">
                <p className="text-sm font-medium mb-2">Edge Color: Standardised Effect Size</p>
                <div className="relative">
                  <div className="flex items-center rounded-md overflow-hidden h-6">
                    <div className="h-6 w-full bg-gradient-to-r from-blue-600 via-yellow-400 to-red-600"></div>
                  </div>
                  <div className="flex justify-between text-xs mt-1">
                    <span>Negative</span>
                    <span className="relative">
                      Zero
                      <div className="absolute left-1/2 -top-8 transform -translate-x-1/2 w-0.5 h-6 bg-black dark:bg-white"></div>
                    </span>
                    <span>Positive</span>
                  </div>
                </div>
              </div>

              <div className="mb-4">
                <p className="text-sm font-medium mb-2">Edge Width: Number of Studies</p>
                <div className="flex flex-col gap-2 pl-2">
                  <div className="flex items-center">
                    <div className="h-1 w-16 bg-gray-500 rounded-full"></div>
                    <span className="ml-3 text-xs">Fewer studies</span>
                  </div>
                  <div className="flex items-center">
                    <div className="h-4 w-16 bg-gray-500 rounded-full"></div>
                    <span className="ml-3 text-xs">More studies</span>
                  </div>
                </div>
              </div>

              <div>
                <p className="text-sm font-medium mb-2">Node Colors</p>
                <div className="flex flex-col gap-2 pl-2">
                  <div className="flex items-center">
                    <div className="h-6 w-6 rounded-full bg-blue-500"></div>
                    <span className="ml-3 text-sm">Predictor only</span>
                  </div>
                  <div className="flex items-center">
                    <div className="h-6 w-6 rounded-full bg-green-500"></div>
                    <span className="ml-3 text-sm">Outcome only</span>
                  </div>
                  <div className="flex items-center">
                    <div className="h-6 w-6 rounded-full bg-purple-500"></div>
                    <span className="ml-3 text-sm">Both predictor and outcome</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Visualization Settings */}
        <div className={`mb-6 p-4 rounded-lg shadow-sm ${
          darkMode ? 'bg-gray-800 border border-gray-700' : 'bg-white border border-gray-200'
        }`}>
          <div className="flex flex-wrap justify-between items-center mb-3">
            <h2 className="text-lg font-bold">Visualisation Settings</h2>
            <div className="flex gap-2">
              <button 
                onClick={resetAllSettings}
                className="px-3 py-1 rounded-md text-sm transition-colors bg-blue-500 text-white hover:bg-blue-400"
              >
                Reset All Settings
              </button>
            </div>
          </div>

          <div className="mb-4">
            <div className="flex border-b border-gray-300 dark:border-gray-700">
              <button 
                onClick={() => setActiveTab('nodes')}
                className={`px-4 py-2 -mb-px text-sm font-medium ${
                  activeTab === 'nodes' ? 'text-gray-700 border-b-2 border-blue-500' : 
                  'text-gray-500 hover:text-gray-700'
                }`}
              >
                Nodes
              </button>
              <button 
                onClick={() => setActiveTab('edges')}
                className={`px-4 py-2 -mb-px text-sm font-medium ${
                  activeTab === 'edges' ? 'text-gray-700 border-b-2 border-blue-500' : 
                  'text-gray-500 hover:text-gray-700'
                }`}
              >
                Edges
              </button>
              <button 
                onClick={() => setActiveTab('attributes')}
                className={`px-4 py-2 -mb-px text-sm font-medium ${
                  activeTab === 'attributes' ? 'text-gray-700 border-b-2 border-blue-500' : 
                  'text-gray-500 hover:text-gray-700'
                }`}
              >
                Attributes
              </button>
            </div>
          </div>

          {activeTab === 'attributes' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-md font-medium mb-3">Filter by Attributes</h3>
                <p className="text-sm mb-4">Select which columns to filter by and their values:</p>
                
                <div className="space-y-4 max-h-80 overflow-y-auto pr-2">
                  {/* Effect size type */}
                  <div className="border-b pb-3 border-gray-200 dark:border-gray-700">
                    <div className="flex justify-between items-center mb-2">
                      <span className="font-medium">Effect size type</span>
                      <div className="flex gap-2">
                        <button 
                          onClick={() => selectAllFilter('effectSizeType')}
                          className="text-xs px-2 py-1 rounded bg-gray-300 text-gray-800 hover:bg-gray-400 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
                        >
                          Select All
                        </button>
                        <button 
                          onClick={() => clearAllFilter('effectSizeType')}
                          className="text-xs px-2 py-1 rounded bg-gray-300 text-gray-800 hover:bg-gray-400 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
                        >
                          Clear All
                        </button>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {getUniqueValues('Effect size type').map(value => (
                        <button
                          key={value}
                          onClick={() => toggleFilter('effectSizeType', value)}
                          className={`px-3 py-1 rounded-md text-xs transition-colors duration-200 ${
                            filters.effectSizeType.includes(value) 
                              ? 'bg-blue-500 text-white hover:bg-blue-400' 
                              : 'bg-gray-200 text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600'
                          }`}
                        >
                          {value}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Location */}
                  <div className="border-b pb-3 border-gray-200 dark:border-gray-700">
                    <div className="flex justify-between items-center mb-2">
                      <span className="font-medium">Location</span>
                      <div className="flex gap-2">
                        <button 
                          onClick={() => selectAllFilter('location')}
                          className="text-xs px-2 py-1 rounded bg-gray-300 text-gray-800 hover:bg-gray-400 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
                        >
                          Select All
                        </button>
                        <button 
                          onClick={() => clearAllFilter('location')}
                          className="text-xs px-2 py-1 rounded bg-gray-300 text-gray-800 hover:bg-gray-400 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
                        >
                          Clear All
                        </button>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {getUniqueValues('Location').map(value => (
                        <button
                          key={value}
                          onClick={() => toggleFilter('location', value)}
                          className={`px-3 py-1 rounded-md text-xs transition-colors duration-200 ${
                            filters.location.includes(value) 
                              ? 'bg-blue-500 text-white hover:bg-blue-400' 
                              : 'bg-gray-200 text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600'
                          }`}
                        >
                          {value}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Study type */}
                  <div className="border-b pb-3 border-gray-200 dark:border-gray-700">
                    <div className="flex justify-between items-center mb-2">
                      <span className="font-medium">Study type</span>
                      <div className="flex gap-2">
                        <button 
                          onClick={() => selectAllFilter('studyType')}
                          className="text-xs px-2 py-1 rounded bg-gray-300 text-gray-800 hover:bg-gray-400 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
                        >
                          Select All
                        </button>
                        <button 
                          onClick={() => clearAllFilter('studyType')}
                          className="text-xs px-2 py-1 rounded bg-gray-300 text-gray-800 hover:bg-gray-400 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
                        >
                          Clear All
                        </button>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {getUniqueValues('Study type').map(value => (
                        <button
                          key={value}
                          onClick={() => toggleFilter('studyType', value)}
                          className={`px-3 py-1 rounded-md text-xs transition-colors duration-200 ${
                            filters.studyType.includes(value) 
                              ? 'bg-blue-500 text-white hover:bg-blue-400' 
                              : 'bg-gray-200 text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600'
                          }`}
                        >
                          {value}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* URL */}
                  <div className="border-b pb-3 border-gray-200 dark:border-gray-700">
                    <div className="flex justify-between items-center mb-2">
                      <span className="font-medium">URL</span>
                      <div className="flex gap-2">
                        <button 
                          onClick={() => selectAllFilter('url')}
                          className="text-xs px-2 py-1 rounded bg-gray-300 text-gray-800 hover:bg-gray-400 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
                        >
                          Select All
                        </button>
                        <button 
                          onClick={() => clearAllFilter('url')}
                          className="text-xs px-2 py-1 rounded bg-gray-300 text-gray-800 hover:bg-gray-400 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
                        >
                          Clear All
                        </button>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {getUniqueValues('URL').map(value => (
                        <button
                          key={value}
                          onClick={() => toggleFilter('url', value)}
                          className={`px-3 py-1 rounded-md text-xs transition-colors duration-200 ${
                            filters.url.includes(value) 
                              ? 'bg-blue-500 text-white hover:bg-blue-400' 
                              : 'bg-gray-200 text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600'
                          }`}
                        >
                          {value}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              <div>
                <h3 className="text-md font-medium mb-3">Display Columns</h3>
                <p className="text-sm mb-2">Select which columns to display in the edge details table:</p>
                <div className="flex gap-2 mb-3">
                  <button 
                    onClick={() => setDisplayColumns([
                      'Effect size', 'Effect size type', 'Location', 'Sample size', 
                      'Standardised effect size', 'Study type', 'URL'
                    ])}
                    className="text-xs px-2 py-1 rounded bg-gray-300 text-gray-800 hover:bg-gray-400 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
                  >
                    Select All
                  </button>
                  <button 
                    onClick={() => setDisplayColumns([])}
                    className="text-xs px-2 py-1 rounded bg-gray-300 text-gray-800 hover:bg-gray-400 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
                  >
                    Clear All
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {['Effect size', 'Effect size type', 'Location', 'Sample size', 'Standardised effect size', 'Study type', 'URL'].map(col => (
                    <button
                      key={col}
                      onClick={() => setDisplayColumns(prev => 
                        prev.includes(col) ? prev.filter(c => c !== col) : [...prev, col]
                      )}
                      className={`px-3 py-1 rounded-md text-sm transition-colors duration-200 ${
                        displayColumns.includes(col) 
                          ? 'bg-blue-500 text-white hover:bg-blue-400' 
                          : 'bg-gray-200 text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600'
                      }`}
                    >
                      {col}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                  Note: &quot;Standardised effect size&quot; is always displayed as the first column.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Tips */}
        <div className={`mt-6 text-sm rounded-lg p-4 ${
          darkMode ? 'bg-blue-900 text-blue-100' : 'bg-blue-50 text-blue-800'
        }`}>
          <p className="mb-1"><strong>Tips:</strong></p>
          <ul className="list-disc ml-5">
            <li>Drag nodes to rearrange the network layout</li>
            <li>Use the zoom controls (<span className="font-bold">+</span>/<span className="font-bold">⊙</span>/<span className="font-bold">−</span>) or mouse wheel to zoom in/out</li>
            <li>Pan the visualization by clicking and dragging the background</li>
            <li>Click on nodes to see their connections</li>
            <li>Click on edges to see detailed relationship information</li>
            <li>Use the Nodes, Edges, and Attributes filters to customize your visualization</li>
            <li>Upload your own CSV data with the required column structure</li>
            <li>Required columns: Predictor, Outcome, Effect size, Standardised effect size, Effect size type, Study type, Sample size, Location</li>
          </ul>
        </div>
      </div>
    </div>
  );
}