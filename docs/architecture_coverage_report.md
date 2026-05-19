# Aokiro Dataset Coverage & Architecture Report

## Overview
This report details the datasets generated during the **DATASET MINING + TRAINING phase**.

## Global Statistics
- **Total Repositories Processed:** 2
- **Total Architectural Nodes Extracted:** 531
- **Total Architectural Edges Mapped:** 875
- **Total QLoRA Instruction Pairs:** 0

## Repository Breakdown

### gocart
- Nodes: 482
- Total Edges: 800
- Cross-File Imports Resolved: 21
- Cross-File Socket Flows Mapped: 0

### project_video_chat
- Nodes: 49
- Total Edges: 75
- Cross-File Imports Resolved: 3
- Cross-File Socket Flows Mapped: 0

## Limitations & Future Scaling Paths
- **Memory Footprint**: Extremely large monorepos (>5,000 files) will produce massively dense graphs, causing `NetworkX` traversal to bottleneck.
- **Dynamic Routing**: Express/Next.js routes mapped as strings (e.g., `app.use('/api', router)`) require more complex Regex pattern matching to build explicit cross-file route edges.
- **LLM Summary Speed**: Generating 10,000 architectural summaries locally on a 7B model will take considerable time (estimated ~10-20 seconds per summary). Batching or cloud-offloading during dataset creation may be required for V3.
