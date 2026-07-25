import cytoscape, { Core, EdgeSingular, EventObject, NodeSingular } from "cytoscape";
import { createIcons, Maximize2, RefreshCw, Search, X } from "lucide";
import type { EntityView, EventView, GraphEdge, GraphNode, GraphView, InteractionView, StatusView } from "./types";
import "./styles.css";

const byId = <T extends HTMLElement>(id: string): T => {
  const element = document.getElementById(id);
  if (!(element instanceof HTMLElement)) throw new Error(`Missing element #${id}`);
  return element as T;
};

const state: {
  graph: GraphView;
  entities: EntityView[];
  interactions: InteractionView[];
  events: EventView[];
  selectedId: string | null;
  selectedKind: "node" | "edge" | null;
} = {
  graph: { nodes: [], edges: [], total_nodes: 0, total_edges: 0, truncated: false },
  entities: [],
  interactions: [],
  events: [],
  selectedId: null,
  selectedKind: null,
};

let cy: Core | null = null;
let firstGraphLoad = true;
let searchTimer = 0;
let graphTopology = "";

createIcons({ icons: { Search, Maximize2, RefreshCw, X } });
wireNavigation();
wireControls();
void refreshAll();
window.setInterval(() => void refreshAll(false), 3_000);

function wireNavigation(): void {
  document.querySelectorAll<HTMLButtonElement>(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      const view = button.dataset.view;
      if (!view) return;
      document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("is-active", tab === button));
      document.querySelectorAll(".view").forEach((panel) => {
        panel.classList.toggle("is-active", panel.id === `${view}-view`);
      });
      if (view === "graph") requestAnimationFrame(() => cy?.resize());
    });
  });
}

function wireControls(): void {
  const scheduleGraphRefresh = (): void => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => void refreshGraph(true), 180);
  };
  byId<HTMLInputElement>("graph-search").addEventListener("input", scheduleGraphRefresh);
  byId<HTMLSelectElement>("entity-filter").addEventListener("change", () => void refreshGraph(true));
  byId<HTMLSelectElement>("edge-filter").addEventListener("change", () => void refreshGraph(true));
  byId<HTMLButtonElement>("fit-graph").addEventListener("click", () => cy?.fit(undefined, 48));
  byId<HTMLButtonElement>("refresh-graph").addEventListener("click", () => void refreshAll(true));
  byId<HTMLButtonElement>("close-inspector").addEventListener("click", clearSelection);
  byId<HTMLInputElement>("entity-search").addEventListener("input", renderEntityTable);
}

async function refreshAll(reposition = false): Promise<void> {
  try {
    const [status, graph, entities, interactions, events] = await Promise.all([
      getJson<StatusView>("/api/v1/status"),
      fetchGraph(),
      getJson<EntityView[]>("/api/v1/entities?limit=500"),
      getJson<InteractionView[]>("/api/v1/interactions?limit=500"),
      getJson<EventView[]>("/api/v1/events?limit=200"),
    ]);
    state.graph = graph;
    state.entities = entities;
    state.interactions = interactions;
    state.events = events;
    renderStatus(status);
    renderGraph(reposition || firstGraphLoad);
    renderEntityTable();
    renderInteractionTable();
    renderEventTable();
    updateFilterOptions();
    refreshInspector();
    firstGraphLoad = false;
  } catch (error) {
    renderDisconnected(error);
  }
}

async function refreshGraph(reposition: boolean): Promise<void> {
  try {
    state.graph = await fetchGraph();
    renderGraph(reposition);
    updateFilterOptions();
    refreshInspector();
  } catch (error) {
    renderDisconnected(error);
  }
}

function fetchGraph(): Promise<GraphView> {
  const params = new URLSearchParams();
  const query = byId<HTMLInputElement>("graph-search").value.trim();
  const entityType = byId<HTMLSelectElement>("entity-filter").value;
  const edgeType = byId<HTMLSelectElement>("edge-filter").value;
  if (query) params.set("q", query);
  if (entityType) params.set("entity_type", entityType);
  if (edgeType) params.set("edge_type", edgeType);
  const suffix = params.size ? `?${params.toString()}` : "";
  return getJson<GraphView>(`/api/v1/graph${suffix}`);
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return (await response.json()) as T;
}

function renderStatus(status: StatusView): void {
  byId("interaction-count").textContent = formatCount(status.interactions);
  byId("entity-count").textContent = formatCount(status.entities);
  byId("edge-count").textContent = formatCount(status.edges);
  const dot = byId("status-dot");
  dot.classList.toggle("is-online", status.consumer_running);
  dot.classList.toggle("is-offline", !status.consumer_running);
  byId("status-label").textContent = status.consumer_running ? "Live projection" : status.consumer_error ?? "Disconnected";
}

function renderDisconnected(error: unknown): void {
  byId("status-dot").className = "status-dot is-offline";
  byId("status-label").textContent = error instanceof Error ? error.message : "Disconnected";
}

function renderGraph(reposition: boolean): void {
  const container = byId("graph-canvas");
  const nodeElements = state.graph.nodes.map((node) => ({
      group: "nodes" as const,
      data: {
        id: node.id,
        label: nodeLabel(node),
        entityType: node.type,
        family: entityFamily(node.type),
        interactions: node.interaction_count,
      },
    }));
  const edgeElements = state.graph.edges.map((edge) => ({
      group: "edges" as const,
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.type,
        interactions: edge.interaction_count,
      },
    }));
  const elements = [...nodeElements, ...edgeElements];
  const nextTopology = [
    ...nodeElements.map((element) => `n:${element.data.id}`),
    ...edgeElements.map(
      (element) => `e:${element.data.id}:${element.data.source}:${element.data.target}`,
    ),
  ]
    .sort()
    .join("|");
  const topologyChanged = nextTopology !== graphTopology;

  byId("graph-empty").toggleAttribute("hidden", elements.length > 0);
  if (cy === null) {
    cy = cytoscape({
      container,
      elements,
      wheelSensitivity: 0.18,
      minZoom: 0.15,
      maxZoom: 2.5,
      style: [
        {
          selector: "node",
          style: {
            width: 46,
            height: 46,
            "background-color": "#e8ece8",
            "border-color": "#58645c",
            "border-width": 2,
            label: "data(label)",
            color: "#18201b",
            "font-family": "Inter, Segoe UI, sans-serif",
            "font-size": 11,
            "text-wrap": "wrap",
            "text-max-width": "120px",
            "text-valign": "bottom",
            "text-margin-y": 9,
            "text-background-color": "#f8faf8",
            "text-background-opacity": 0.92,
            "text-background-padding": "2px",
          },
        },
        { selector: 'node[family = "service"]', style: { "background-color": "#d8eee9", "border-color": "#087f6d" } },
        { selector: 'node[family = "k8s"]', style: { "background-color": "#e5eaf8", "border-color": "#4169a1" } },
        { selector: 'node[family = "app"]', style: { "background-color": "#fff0cf", "border-color": "#b36b00" } },
        { selector: 'node[family = "runtime"]', style: { "background-color": "#f1e6f3", "border-color": "#7e5686" } },
        {
          selector: "edge",
          style: {
            width: "mapData(interactions, 1, 10, 1.5, 5)",
            "line-color": "#9ca59f",
            "target-arrow-color": "#657169",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(label)",
            color: "#4f5952",
            "font-size": 10,
            "text-background-color": "#ffffff",
            "text-background-opacity": 0.9,
            "text-background-padding": "3px",
            "text-rotation": "autorotate",
          },
        },
        {
          selector: ":selected",
          style: {
            "border-color": "#d64045",
            "line-color": "#d64045",
            "target-arrow-color": "#d64045",
            "border-width": 4,
          },
        },
      ],
    });
    cy.on("tap", "node", (event: EventObject) => selectNode(event.target as NodeSingular));
    cy.on("tap", "edge", (event: EventObject) => selectEdge(event.target as EdgeSingular));
    cy.on("tap", (event: EventObject) => {
      if (event.target === cy) clearSelection();
    });
  } else if (topologyChanged) {
    cy.elements().remove();
    cy.add(elements);
  } else {
    nodeElements.forEach((element) => cy?.getElementById(element.data.id).data(element.data));
    edgeElements.forEach((element) => cy?.getElementById(element.data.id).data(element.data));
  }

  if ((reposition || topologyChanged) && elements.length > 0) {
    cy.layout({
      name: "cose",
      animate: false,
      fit: true,
      padding: 48,
      nodeRepulsion: () => 14_000,
      idealEdgeLength: () => 140,
    }).run();
    if (cy.zoom() > 1.25) {
      cy.zoom(1.25);
      cy.center();
    }
  }
  graphTopology = nextTopology;
}

function selectNode(node: NodeSingular): void {
  state.selectedKind = "node";
  state.selectedId = node.id();
  refreshInspector();
}

function selectEdge(edge: EdgeSingular): void {
  state.selectedKind = "edge";
  state.selectedId = edge.id();
  refreshInspector();
}

function clearSelection(): void {
  state.selectedKind = null;
  state.selectedId = null;
  cy?.elements().unselect();
  byId("inspector").classList.remove("is-open");
}

function refreshInspector(): void {
  if (!state.selectedId || !state.selectedKind) return;
  const item =
    state.selectedKind === "node"
      ? state.graph.nodes.find((node) => node.id === state.selectedId)
      : state.graph.edges.find((edge) => edge.id === state.selectedId);
  if (!item) {
    clearSelection();
    return;
  }
  const inspector = byId("inspector");
  inspector.classList.add("is-open");
  byId("inspector-kind").textContent = state.selectedKind === "node" ? "Entity" : "Relationship";
  byId("inspector-title").textContent =
    state.selectedKind === "node" ? (item as GraphNode).type : (item as GraphEdge).type;
  byId("inspector-body").innerHTML =
    state.selectedKind === "node" ? nodeInspector(item as GraphNode) : edgeInspector(item as GraphEdge);
}

function nodeInspector(node: GraphNode): string {
  return `
    ${detailRow("ID", node.id)}
    ${detailRow("Type", node.type)}
    ${detailRow("Interactions", String(node.interaction_count))}
    <h3>Attributes</h3>
    ${objectRows(node.attributes)}
  `;
}

function edgeInspector(edge: GraphEdge): string {
  return `
    ${detailRow("Source", edge.source)}
    ${detailRow("Target", edge.target)}
    ${detailRow("Type", edge.type)}
    ${detailRow("Interactions", String(edge.interaction_count))}
    <h3>Attributes</h3>
    ${objectRows(edge.attributes)}
  `;
}

function renderEntityTable(): void {
  const query = byId<HTMLInputElement>("entity-search").value.trim().toLowerCase();
  const rows = state.entities.filter(
    (entity) =>
      !query ||
      entity.id.toLowerCase().includes(query) ||
      entity.type.toLowerCase().includes(query) ||
      JSON.stringify(entity.attributes).toLowerCase().includes(query),
  );
  byId<HTMLTableElement>("entities-table").innerHTML = table(
    ["Type", "Entity ID", "Interactions", "Attributes"],
    rows.map((entity) => [
      badge(entity.type),
      `<code>${escapeHtml(entity.id)}</code>`,
      String(entity.interaction_count),
      compactObject(entity.attributes),
    ]),
  );
}

function renderInteractionTable(): void {
  byId<HTMLTableElement>("interactions-table").innerHTML = table(
    ["Client", "Relationship", "Server", "Metrics", "Observed"],
    state.interactions.map((interaction) => [
      escapeHtml(interaction.client),
      badge(interaction.connection_type),
      escapeHtml(interaction.server),
      compactObject(interaction.metrics),
      formatTime(interaction.emitted_at_unix_ms),
    ]),
  );
}

function renderEventTable(): void {
  byId<HTMLTableElement>("events-table").innerHTML = table(
    ["Operation", "Interaction", "Schema", "Partition / offset", "Emitted"],
    state.events.map((event) => [
      `<span class="operation operation-${event.operation}">${escapeHtml(event.operation)}</span>`,
      `<code>${escapeHtml(shortId(event.interaction_id))}</code>`,
      escapeHtml(event.schema_version),
      `${event.partition} / ${event.offset}`,
      formatTime(event.emitted_at_unix_ms),
    ]),
  );
}

function updateFilterOptions(): void {
  updateSelect("entity-filter", "All entity types", [...new Set(state.graph.nodes.map((node) => node.type))]);
  updateSelect("edge-filter", "All relationships", [...new Set(state.graph.edges.map((edge) => edge.type))]);
}

function updateSelect(id: string, emptyLabel: string, values: string[]): void {
  const select = byId<HTMLSelectElement>(id);
  const current = select.value;
  select.innerHTML = `<option value="">${emptyLabel}</option>${values
    .sort()
    .map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`)
    .join("")}`;
  if (values.includes(current)) select.value = current;
}

function nodeLabel(node: GraphNode): string {
  const attribute = (key: string): string | null => {
    const value = node.attributes[key];
    return typeof value === "string" && value.length > 0 ? value : null;
  };
  const preferredKeys: Record<string, string[]> = {
    service: ["service.name"],
    "service.namespace": ["service.namespace"],
    "service.instance": ["service.instance.id"],
    "k8s.namespace": ["k8s.namespace.name"],
    "k8s.pod": ["k8s.pod.name", "k8s.pod.uid"],
    "k8s.deployment": ["k8s.deployment.name", "k8s.deployment.uid"],
  };
  if (node.type === "app.endpoint") {
    const route = attribute("http.route");
    const method = attribute("http.request.method");
    if (route) return method ? `${method} ${route}` : route;
  }
  for (const key of preferredKeys[node.type] ?? []) {
    const value = attribute(key);
    if (value) return value;
  }
  const nameEntry = Object.entries(node.attributes).find(
    ([key, value]) => (key.endsWith(".name") || key.endsWith(".id")) && typeof value === "string",
  );
  if (nameEntry && typeof nameEntry[1] === "string") return nameEntry[1];
  const fallback = decodeURIComponent(node.id.split(":").at(-1) ?? node.id);
  return fallback.length > 28 ? `${fallback.slice(0, 25)}...` : fallback;
}

function entityFamily(type: string): string {
  if (type.startsWith("service")) return "service";
  if (type.startsWith("k8s")) return "k8s";
  if (type.startsWith("app")) return "app";
  if (type.startsWith("process") || type.startsWith("container") || type.startsWith("telemetry")) return "runtime";
  return "other";
}

function table(headers: string[], rows: string[][]): string {
  return `
    <thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
    <tbody>${
      rows.length
        ? rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")
        : `<tr><td colspan="${headers.length}" class="table-empty">No records</td></tr>`
    }</tbody>
  `;
}

function detailRow(label: string, value: string): string {
  return `<div class="detail-row"><span>${escapeHtml(label)}</span><code>${escapeHtml(value)}</code></div>`;
}

function objectRows(value: Record<string, unknown>): string {
  const entries = Object.entries(value);
  return entries.length
    ? entries.map(([key, item]) => detailRow(key, formatValue(item))).join("")
    : '<div class="muted">None</div>';
}

function compactObject(value: Record<string, unknown>): string {
  const entries = Object.entries(value);
  if (!entries.length) return '<span class="muted">None</span>';
  return entries
    .slice(0, 3)
    .map(([key, item]) => `<span class="compact-value"><b>${escapeHtml(key)}</b> ${escapeHtml(formatValue(item))}</span>`)
    .join("");
}

function badge(value: string): string {
  return `<span class="type-badge">${escapeHtml(value)}</span>`;
}

function formatValue(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}

function formatTime(unixMs: number): string {
  return new Date(unixMs).toLocaleString();
}

function formatCount(value: number): string {
  return new Intl.NumberFormat().format(value);
}

function shortId(value: string): string {
  return value.length > 18 ? `${value.slice(0, 10)}…${value.slice(-6)}` : value;
}

function escapeHtml(value: string): string {
  return value.replace(
    /[&<>"']/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
      })[character] ?? character,
  );
}
