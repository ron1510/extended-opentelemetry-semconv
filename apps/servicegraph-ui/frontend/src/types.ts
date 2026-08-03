export type JsonObject = Record<string, unknown>;

export interface GraphNode {
  kind: "node";
  id: string;
  type: string;
  attributes: JsonObject;
}

export interface GraphEdgeElement {
  kind: "edge";
  id: string;
  type: string;
  source_id: string;
  target_id: string;
  attributes: JsonObject;
  metrics: Record<string, number>;
}

export type GraphElement = GraphNode | GraphEdgeElement;

export interface GraphEdge {
  kind: "edge";
  id: string;
  source: string;
  target: string;
  type: string;
  attributes: JsonObject;
  metrics: Record<string, number>;
}

export interface GraphView {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_nodes: number;
  total_edges: number;
  truncated: boolean;
}

export interface EventView {
  event_id: string;
  operation: "upsert" | "delete";
  element_id: string;
  schema_version: "2.0";
  observed_at_unix_nano: number;
  emitted_at_unix_ms: number;
  partition: number;
  offset: number;
}

export interface StatusView {
  consumer_running: boolean;
  consumer_error: string | null;
  topic: string;
  elements: number;
  nodes: number;
  edges: number;
  last_event_at_unix_ms: number | null;
}
