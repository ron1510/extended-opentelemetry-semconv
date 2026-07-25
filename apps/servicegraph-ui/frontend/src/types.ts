export type JsonObject = Record<string, unknown>;

export interface GraphNode {
  id: string;
  type: string;
  attributes: JsonObject;
  interaction_count: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  attributes: JsonObject;
  interaction_ids: string[];
  interaction_count: number;
}

export interface GraphView {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_nodes: number;
  total_edges: number;
  truncated: boolean;
}

export interface EntityView extends GraphNode {
  interaction_ids: string[];
}

export interface InteractionView {
  interaction_id: string;
  client: string;
  server: string;
  connection_type: string;
  dimensions: JsonObject;
  metrics: Record<string, number>;
  entities: Array<{ id: string; type: string }>;
  observed_at_unix_nano: number;
  emitted_at_unix_ms: number;
  payload_hash: string;
}

export interface EventView {
  event_id: string;
  operation: "upsert" | "delete";
  interaction_id: string;
  schema_version: "1.0" | "1.1";
  observed_at_unix_nano: number;
  emitted_at_unix_ms: number;
  partition: number;
  offset: number;
}

export interface StatusView {
  consumer_running: boolean;
  consumer_error: string | null;
  topic: string;
  interactions: number;
  entities: number;
  edges: number;
  last_event_at_unix_ms: number | null;
}
