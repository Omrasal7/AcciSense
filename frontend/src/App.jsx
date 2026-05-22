import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Building2,
  Camera,
  Hospital,
  LayoutDashboard,
  MapPinned,
  Phone,
  Shield,
  Trash2,
  Upload,
  UserCog,
  Users,
} from "lucide-react";
import { DivIcon } from "leaflet";
import { MapContainer, Marker, Popup, TileLayer, Tooltip } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import {
  analyzeIncident,
  createContact,
  deleteContact,
  deleteIncident,
  fetchCameraSources,
  fetchContacts,
  fetchIncidents,
} from "./api";
import cameraCardImage from "./ChatGPT Image May 22, 2026, 06_41_00 PM.png";

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

const emptyContact = { name: "", phone: "", email: "", relation: "" };
const API_ORIGIN = (import.meta.env.VITE_API_BASE || "http://localhost:8001/api/v1").replace(/\/api\/v1\/?$/, "");

const liveLocationIcon = new DivIcon({
  className: "accident-live-marker",
  html: `
    <div class="accident-marker-shell">
      <span class="accident-marker-pulse"></span>
      <span class="accident-marker-core"></span>
    </div>
  `,
  iconSize: [44, 44],
  iconAnchor: [22, 22],
});

const NAV_ITEMS = [
  { key: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { key: "incidents", label: "Incidents", icon: AlertTriangle },
  { key: "cameras", label: "Cameras", icon: Camera },
  { key: "map", label: "Map", icon: MapPinned },
  { key: "admin", label: "Admin", icon: UserCog },
];

const HERO_COPY = {
  dashboard: {
    title: "Emergency operations, designed for clarity.",
    description: "Track active incidents, review severity, and coordinate dispatch decisions from a single operational overview.",
    primaryMetric: { label: "Tracked", key: "active", tone: "navy" },
    secondaryMetric: { label: "Critical", key: "critical", tone: "critical" },
    tertiaryMetric: { label: "High", key: "high", tone: "warning" },
    quaternaryMetric: { label: "Mapped", key: "mapped", tone: "green" },
  },
  incidents: {
    title: "Incident intake and review.",
    description: "Upload evidence, trigger AI analysis, and review the latest processed incidents with alert delivery context.",
    primaryMetric: { label: "Uploads", key: "active", tone: "blue" },
    secondaryMetric: { label: "Reviewing", key: "high", tone: "warning" },
    tertiaryMetric: { label: "Critical", key: "critical", tone: "critical" },
    quaternaryMetric: { label: "Sources", key: "cameras", tone: "navy" },
  },
  cameras: {
    title: "Registered camera network.",
    description: "Inspect the source registry that powers automatic location resolution when uploaded evidence has no embedded GPS data.",
    primaryMetric: { label: "Cameras", key: "cameras", tone: "blue" },
    secondaryMetric: { label: "Mapped", key: "mapped", tone: "green" },
    tertiaryMetric: { label: "Tracked", key: "active", tone: "navy" },
    quaternaryMetric: { label: "Critical", key: "critical", tone: "critical" },
  },
  map: {
    title: "Live mapped scene intelligence.",
    description: "Keep the most recent resolved incident location front and center with a continuous geospatial operating view.",
    primaryMetric: { label: "Mapped", key: "mapped", tone: "green" },
    secondaryMetric: { label: "Tracked", key: "active", tone: "navy" },
    tertiaryMetric: { label: "High", key: "high", tone: "warning" },
    quaternaryMetric: { label: "Cameras", key: "cameras", tone: "blue" },
  },
  admin: {
    title: "Admin routing and alert control.",
    description: "Manage the single notification profile used for verified incident outreach across SMS and email channels.",
    primaryMetric: { label: "Tracked", key: "active", tone: "navy" },
    secondaryMetric: { label: "Cameras", key: "cameras", tone: "blue" },
    tertiaryMetric: { label: "Mapped", key: "mapped", tone: "green" },
    quaternaryMetric: { label: "Critical", key: "critical", tone: "critical" },
  },
};

class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen bg-[#F5F7FA] px-4 py-10 text-slate-900">
          <div className="mx-auto max-w-3xl rounded-[28px] border border-red-200 bg-white p-6 shadow-sm">
            <div className="text-sm font-semibold text-red-600">Frontend runtime error</div>
            <div className="mt-3 text-2xl font-semibold text-slate-950">The dashboard hit a render error.</div>
            <pre className="mt-4 overflow-auto whitespace-pre-wrap rounded-2xl bg-slate-950 p-4 text-sm leading-6 text-red-100">
              {String(this.state.error?.message || this.state.error)}
            </pre>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default function App() {
  const [currentPage, setCurrentPage] = useState(getPageFromHash());
  const [incidents, setIncidents] = useState([]);
  const [contacts, setContacts] = useState([]);
  const [cameraSources, setCameraSources] = useState([]);
  const [contactForm, setContactForm] = useState(emptyContact);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [selectedFile, setSelectedFile] = useState(null);
  const [selectedSourceId, setSelectedSourceId] = useState("");
  const [uploadInputKey, setUploadInputKey] = useState(0);
  const [liveNow, setLiveNow] = useState(() => new Date());

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setLiveNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const handleHashChange = () => setCurrentPage(getPageFromHash());
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  async function loadData() {
    try {
      const [incidentData, contactData, cameraSourceData] = await Promise.all([
        fetchIncidents(),
        fetchContacts(),
        fetchCameraSources(),
      ]);
      setIncidents(incidentData);
      setContacts(contactData);
      setCameraSources(cameraSourceData);
    } catch (err) {
      setError(err.message);
    }
  }

  async function submitIncidentAnalysis(file, sourceId = "") {
    const form = new FormData();
    form.append("image", file);
    if (sourceId) {
      form.append("source_id", sourceId);
    }

    setUploading(true);
    setError("");
    try {
      const result = await analyzeIncident(form);
      setIncidents((current) => [result.incident, ...current]);
      setSelectedFile(null);
      setSelectedSourceId("");
      setUploadInputKey((current) => current + 1);
      window.location.hash = "incidents";
    } catch (err) {
      setSelectedFile((current) => (current ? { ...current, analysisState: "error" } : current));
      setError(err.message);
    } finally {
      setUploading(false);
    }
  }

  async function handleAnalyze(event) {
    event.preventDefault();
    const file = event.currentTarget.elements.image?.files?.[0];
    if (!file) {
      setError("Select an image or video first.");
      return;
    }
    if (!selectedSourceId) {
      setError("Select a camera source before analysis.");
      return;
    }

    await submitIncidentAnalysis(file, selectedSourceId);
    event.currentTarget.reset();
  }

  async function handleContactSubmit(event) {
    event.preventDefault();
    setError("");
    try {
      const saved = await createContact(contactForm);
      setContacts([saved]);
      setContactForm(emptyContact);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDeleteContact(contactId) {
    setError("");
    try {
      await deleteContact(contactId);
      setContacts([]);
      setContactForm(emptyContact);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDeleteIncident(incidentId) {
    setError("");
    try {
      await deleteIncident(incidentId);
      setIncidents((current) => current.filter((incident) => incident.id !== incidentId));
    } catch (err) {
      setError(err.message);
    }
  }

  function handleFileChange(event) {
    const file = event.target.files?.[0] || null;
    if (!file) {
      setSelectedFile(null);
      return;
    }

    setSelectedFile({
      file,
      name: file.name,
      type: file.type,
      url: URL.createObjectURL(file),
      analysisState: isVideoFile(file) ? "ready" : "idle",
    });
  }

  async function handleVideoPlaybackComplete() {
    if (!selectedFile?.file || !isVideoFile(selectedFile) || uploading) {
      return;
    }

    if (selectedFile.analysisState === "running" || selectedFile.analysisState === "complete") {
      return;
    }

    if (!selectedSourceId) {
      setError("Select a camera source before playing the video for automatic analysis.");
      setSelectedFile((current) => (current ? { ...current, analysisState: "error" } : current));
      return;
    }

    setSelectedFile((current) => (current ? { ...current, analysisState: "running" } : current));
    await submitIncidentAnalysis(selectedFile.file, selectedSourceId);
  }

  const latestMappedIncident = incidents.find((item) => item.location?.latitude && item.location?.longitude);
  const accidentIncidents = incidents.filter((item) => item.detection.accident_detected);
  const latestAccident = accidentIncidents[0];
  const activeAdmin = contacts[0] || null;

  const metrics = useMemo(
    () => ({
      active: accidentIncidents.length,
      critical: accidentIncidents.filter((item) => item.severity.score >= 4).length,
      high: accidentIncidents.filter((item) => item.severity.score >= 3).length,
      mapped: accidentIncidents.filter((item) => item.location?.latitude && item.location?.longitude).length,
      cameras: cameraSources.length,
    }),
    [accidentIncidents, cameraSources.length]
  );

  const pageTitle = useMemo(() => NAV_ITEMS.find((item) => item.key === currentPage)?.label || "Dashboard", [currentPage]);

  return (
    <AppErrorBoundary>
      <div className="min-h-screen bg-[#07111f] text-slate-100">
        <div className="mx-auto max-w-[1320px] px-4 py-5 sm:px-6 lg:px-8">
          <TopNav currentPage={currentPage} setCurrentPage={setCurrentPage} metrics={metrics} />

          <HeroSection
            currentPage={currentPage}
            pageTitle={pageTitle}
            metrics={metrics}
            latestAccident={latestAccident}
            latestMappedIncident={latestMappedIncident}
            liveNow={liveNow}
            selectedFile={selectedFile}
          />

          {error ? (
            <div className="mt-4 rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>
          ) : null}

          <main className="mt-6 space-y-6">
            {currentPage === "dashboard" && (
              <DashboardPage
                latestMappedIncident={latestMappedIncident}
                latestAccident={latestAccident}
                activeAdmin={activeAdmin}
                metrics={metrics}
                incidents={incidents}
                onDeleteIncident={handleDeleteIncident}
              />
            )}

            {currentPage === "incidents" && (
              <IncidentsPage
                incidents={incidents}
                cameraSources={cameraSources}
                selectedFile={selectedFile}
                selectedSourceId={selectedSourceId}
                setSelectedSourceId={setSelectedSourceId}
                uploading={uploading}
                uploadInputKey={uploadInputKey}
                onAnalyze={handleAnalyze}
                onDeleteIncident={handleDeleteIncident}
                onFileChange={handleFileChange}
                onVideoPlaybackComplete={handleVideoPlaybackComplete}
              />
            )}

            {currentPage === "cameras" && <CamerasPage cameraSources={cameraSources} />}

            {currentPage === "map" && <MapPage latestMappedIncident={latestMappedIncident} />}

            {currentPage === "admin" && (
              <AdminPage
                activeAdmin={activeAdmin}
                contactForm={contactForm}
                setContactForm={setContactForm}
                onSubmit={handleContactSubmit}
                onDelete={handleDeleteContact}
              />
            )}
          </main>
        </div>
      </div>
    </AppErrorBoundary>
  );
}

function TopNav({ currentPage, setCurrentPage, metrics }) {
  return (
    <header className="rounded-[28px] border border-white/10 bg-white/5 px-5 py-4 shadow-[0_18px_48px_rgba(2,8,23,0.35)] backdrop-blur-xl sm:px-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/8 text-blue-200 ring-1 ring-white/10">
            <Shield size={20} />
          </div>
          <div>
            <div className="text-lg font-semibold tracking-tight text-white">AcciSense</div>
            <div className="text-sm text-slate-400">AI emergency response operations platform</div>
          </div>
        </div>

        <div className="flex flex-col gap-3 lg:items-end">
          <div className="flex flex-wrap items-center gap-3 text-xs font-medium text-slate-400">
            <span className="inline-flex items-center gap-2 rounded-full bg-emerald-400/10 px-3 py-1 text-emerald-300 ring-1 ring-emerald-400/20">
                <span className="status-pulse-dot bg-emerald-400" />
                SYSTEM ONLINE
            </span>
            <span className="inline-flex items-center gap-2 rounded-full bg-white/[0.04] px-3 py-1 text-slate-300 ring-1 ring-white/10">
              {metrics?.cameras || 0} CAMERAS ACTIVE
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
          {NAV_ITEMS.map((item) => (
            <TopNavButton
              key={item.key}
              active={currentPage === item.key}
              icon={item.icon}
              label={item.label}
              onClick={() => {
                window.location.hash = item.key;
                setCurrentPage(item.key);
              }}
            />
          ))}
          </div>
        </div>
      </div>
    </header>
  );
}

function HeroSection({ currentPage, pageTitle, metrics, latestAccident, latestMappedIncident, liveNow, selectedFile }) {
  const heroCopy = HERO_COPY[currentPage] || HERO_COPY.dashboard;
  const metricCards = [
    heroCopy.primaryMetric,
    heroCopy.secondaryMetric,
    heroCopy.tertiaryMetric,
    heroCopy.quaternaryMetric,
  ];

  return (
    <section className="mt-5 rounded-[34px] border border-white/10 bg-[radial-gradient(circle_at_top_left,rgba(56,189,248,0.18),transparent_28%),linear-gradient(180deg,rgba(15,23,42,0.96),rgba(8,15,28,0.98))] px-5 py-6 shadow-[0_28px_80px_rgba(2,8,23,0.45)] sm:px-6 lg:px-8">
      <div className="grid gap-6 lg:grid-cols-[1.02fr_0.98fr] lg:items-stretch">
        <div className="hero-copy-shell max-w-3xl">
          <div className="hero-copy-atmosphere" />
          <div className="hero-live-badge">
            <span className="status-pulse-dot bg-emerald-400" />
            LIVE MONITORING ACTIVE
          </div>
          <h1 className="mt-4 text-3xl font-semibold tracking-tight text-white sm:text-[2.2rem]">
            {heroCopy.title}
          </h1>
          <p className="mt-3 max-w-2xl text-base leading-7 text-slate-300">
            {heroCopy.description}
          </p>

          <div className="hero-status-strip mt-6">
            {metricCards.map((metric) => (
              <HeroMetric key={`${currentPage}-${metric.label}`} title={metric.label} value={metrics[metric.key]} tone={metric.tone} />
            ))}
          </div>
        </div>

        <HeroVisualPanel
          currentPage={currentPage}
          pageTitle={pageTitle}
          latestAccident={latestAccident}
          latestMappedIncident={latestMappedIncident}
          liveNow={liveNow}
          metrics={metrics}
          selectedFile={selectedFile}
        />
      </div>
    </section>
  );
}

function HeroVisualPanel({ currentPage, pageTitle, latestAccident, latestMappedIncident, liveNow, metrics, selectedFile }) {
  const snapshotUrl = latestAccident?.image_url ? `${API_ORIGIN}${latestAccident.image_url}` : "";
  const panelTitles = {
    dashboard: "Operations network overview",
    incidents: "Latest processed incident",
    cameras: "Camera registry activity",
    map: "Mapped scene focus",
    admin: "Alert routing status",
  };
  const panelDescriptions = {
    dashboard: "City-wide monitoring status, camera readiness, and mapped activity across the active network.",
    incidents: latestAccident ? "Newest analyzed incident with saved evidence and severity." : "No incident has been analyzed yet in this session.",
    cameras: metrics.cameras ? `${metrics.cameras} registered camera sources are ready for geolocation matching.` : "No camera sources are currently loaded.",
    map: latestMappedIncident ? "Most recent location-resolved incident available for geospatial review." : "Waiting for a mapped incident to appear in the feed.",
    admin: "Single admin profile controls verified outreach across SMS and email.",
  };

  return (
    <div className="hero-monitor-panel rounded-[28px] border border-white/10 bg-white/5 p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-sm font-medium text-sky-200">{panelTitles[currentPage] || `AcciSense ${pageTitle}`}</div>
          <div className="mt-1 text-sm text-slate-400">
            {panelDescriptions[currentPage] || panelDescriptions.dashboard}
          </div>
        </div>
        <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-slate-950/40 px-3 py-1 text-xs text-slate-300">
          <Activity size={13} />
          {formatLiveClock(liveNow)}
        </span>
      </div>

        <div className="mt-4 overflow-hidden rounded-[24px] border border-white/10 bg-[#08111d]">
          {currentPage === "incidents" ? (
            <div className="hero-simple-panel px-5 py-5">
              <div className="hero-simple-panel__header">
                <span className="hero-simple-badge hero-simple-badge--sky">Review queue</span>
              </div>
              <div className="hero-simple-list mt-4">
                <HeroDetailRow label="Evidence source" value={selectedFile?.name || "Awaiting upload"} tone="sky" />
                <HeroDetailRow label="AI review state" value={latestAccident ? "Latest case processed" : "Queue idle"} tone="blue" />
                <HeroDetailRow label="Severity state" value={latestAccident ? latestAccident.severity?.label || "Reviewed" : "Pending"} tone="warning" />
              </div>
              <div className="structured-hero-strip mt-5">
                <InlineMetricStat tone="blue" label="Latest status" value={latestAccident ? "Processed" : "Waiting"} />
                <InlineMetricStat tone="warning" label="Accident cases" value={metrics.active} />
                <InlineMetricStat tone="green" label="Mapped scenes" value={metrics.mapped} />
              </div>
            </div>
          ) : currentPage === "cameras" ? (
            <div className="hero-simple-panel px-5 py-5">
              <div className="hero-simple-panel__header">
                <span className="hero-simple-badge hero-simple-badge--sky">Camera mesh live</span>
              </div>
              <div className="camera-mesh-canvas mt-4">
                <img className="camera-mesh-image" src={cameraCardImage} alt="Camera network preview" />
                <div className="camera-mesh-stats">
                  <div className="camera-mesh-stat">
                    <div className="camera-mesh-stat__label">Sources online</div>
                    <div className="camera-mesh-stat__value">{metrics.cameras}</div>
                  </div>
                  <div className="camera-mesh-stat">
                    <div className="camera-mesh-stat__label">Mapped incidents</div>
                    <div className="camera-mesh-stat__value">{metrics.mapped}</div>
                  </div>
                  <div className="camera-mesh-stat">
                    <div className="camera-mesh-stat__label">High severity</div>
                    <div className="camera-mesh-stat__value">{metrics.high}</div>
                  </div>
                </div>
              </div>
              <div className="structured-hero-strip mt-5">
                <InlineMetricStat tone="blue" label="Registry status" value="Aligned" />
                <InlineMetricStat tone="green" label="Geo matching" value={metrics.mapped ? "Active" : "Ready"} />
                <InlineMetricStat tone="warning" label="Operator focus" value={metrics.high ? "High severity present" : "Standard monitoring"} />
              </div>
            </div>
          ) : currentPage === "admin" ? (
            <div className="hero-simple-panel px-5 py-5">
              <div className="hero-simple-panel__header hero-simple-panel__header--spread">
                <div>
                  <div className="text-sm font-medium text-emerald-200">Communications routing</div>
                  <div className="mt-1 text-sm text-slate-400">
                    Single admin profile receives verified incident alerts through controlled SMS and email channels.
                  </div>
                </div>
                <span className="hero-simple-badge hero-simple-badge--green">Ready</span>
              </div>

              <div className="routing-flow mt-6">
                <RoutingNode label="Camera" tone="blue" />
                <RoutingNode label="AI" tone="sky" />
                <RoutingNode label="Verification" tone="emerald" />
                <RoutingNode label="SMS / Email" tone="green" />
              </div>

              <div className="hero-simple-list mt-6">
                <StatusRow label="SMS channel" tone="green" value="Ready" />
                <StatusRow label="Email channel" tone="green" value="Ready" />
                <StatusRow label="Mapped scenes" tone="sky" value={metrics.mapped} />
              </div>
            </div>
          ) : currentPage === "map" ? (
            <div className="hero-simple-panel px-5 py-5">
              <div className="hero-simple-panel__header">
                <span className="hero-simple-badge hero-simple-badge--green">
                  {latestMappedIncident?.location?.address ? "Live mapped focus" : "Map focus ready"}
                </span>
              </div>
              <div className="hero-map-surface mt-4">
                <div className="map-grid-surface" />
                <div className="map-hero-route map-hero-route--one" />
                <div className="map-hero-route map-hero-route--two" />
                <div className="absolute left-[50%] top-[48%]">
                  <div className="hero-map-marker">
                    <span className="hero-map-marker__pulse" />
                    <span className="hero-map-marker__core" />
                  </div>
                </div>
                <div className="map-hero-radius left-[50%] top-[48%]" />
                <div className="map-camera-node map-camera-node--a" />
                <div className="map-camera-node map-camera-node--b" />
                <div className="map-camera-node map-camera-node--c" />
              </div>
              <div className="hero-location-panel mt-4">
                <div className="text-sm font-medium text-white">
                  {latestMappedIncident?.location?.source || "Awaiting mapped source"}
                </div>
                <div className="mt-1 text-sm text-slate-400">
                  {latestMappedIncident?.location?.address || "The next mapped incident will lock onto this live city position."}
                </div>
              </div>
              <div className="structured-hero-strip mt-5">
                <InlineMetricStat tone="green" label="Mapped scenes" value={metrics.mapped} />
                <InlineMetricStat tone="blue" label="Cameras online" value={metrics.cameras} />
              </div>
            </div>
          ) : currentPage === "dashboard" ? (
            <div className="hero-simple-panel px-5 py-5">
              <div className="hero-simple-panel__header">
                <span className="hero-simple-badge hero-simple-badge--sky">System operations overview</span>
              </div>
              <div className="dashboard-command-board mt-4">
                <div className="dashboard-command-board__row">
                  <span className="dashboard-command-board__label">Network state</span>
                  <span className="dashboard-command-board__value">{metrics.cameras ? "Nominal" : "Loading"}</span>
                </div>
                <div className="dashboard-command-board__row">
                  <span className="dashboard-command-board__label">Monitoring mode</span>
                  <span className="dashboard-command-board__value">{metrics.active ? "Active response" : "City standby"}</span>
                </div>
                <div className="dashboard-command-board__row">
                  <span className="dashboard-command-board__label">Coverage state</span>
                  <span className="dashboard-command-board__value">{metrics.mapped ? "Mapped scenes live" : "Awaiting mapped event"}</span>
                </div>
              </div>
              <div className="hero-simple-grid mt-4 sm:grid-cols-2">
                <HeroSignalCard label="Active incidents" value={metrics.active || "0"} />
                <HeroSignalCard label="Critical watch" value={metrics.critical ? `${metrics.critical} flagged` : "Clear"} />
              </div>
              <div className="structured-hero-strip mt-5">
                <InlineMetricStat tone="sky" label="Cameras online" value={metrics.cameras} />
                <InlineMetricStat tone="green" label="Mapped scenes" value={metrics.mapped} />
                <InlineMetricStat tone="warning" label="High severity" value={metrics.high} />
              </div>
            </div>
          ) : snapshotUrl ? (
            <div className="relative">
              <img alt="Latest incident" className="h-[260px] w-full object-cover" src={snapshotUrl} />
              <div className="absolute inset-0 bg-gradient-to-t from-[#030712]/85 via-transparent to-transparent" />
            <div className="absolute left-4 right-4 top-4 flex items-center justify-between">
              <span className="inline-flex items-center gap-2 rounded-full bg-emerald-400/10 px-3 py-1 text-xs font-medium text-emerald-300 ring-1 ring-emerald-400/20">
                <span className="status-pulse-dot bg-emerald-400" />
                Live camera ingest
              </span>
              {latestAccident?.severity?.label ? (
                <span className={`rounded-full px-3 py-1 text-xs font-medium ${heroSeverityClass(latestAccident.severity.label)}`}>
                  {latestAccident.severity.label}
                </span>
                ) : null}
              </div>
              <div className="absolute bottom-4 left-4 right-4">
                <div className="structured-hero-strip">
                  <InlineMetricStat tone="blue" label="Confidence" value={`${Math.round((latestAccident?.detection?.confidence || 0) * 100)}%`} />
                  <InlineMetricStat tone="sky" label="Camera" value={latestAccident?.location?.source || "Unresolved"} />
                  <InlineMetricStat tone="green" label="Address" value={latestMappedIncident?.location?.address ? "Mapped" : "Pending"} />
                </div>
              </div>
            </div>
          ) : (
            <div className="hero-simple-panel px-5 py-5">
              <div className="hero-simple-panel__header">
                <span className="hero-simple-badge hero-simple-badge--sky">Operational standby</span>
              </div>
              <div className="dashboard-command-board mt-4">
                <div className="dashboard-command-board__row">
                  <span className="dashboard-command-board__label">Priority scene</span>
                  <span className="dashboard-command-board__value">{metrics.active ? "Active review" : "Standby"}</span>
                </div>
                <div className="dashboard-command-board__row">
                  <span className="dashboard-command-board__label">Network health</span>
                  <span className="dashboard-command-board__value">{metrics.cameras ? "Nominal" : "Loading"}</span>
                </div>
              </div>
              <div className="structured-hero-strip mt-5">
                <InlineMetricStat tone="blue" label="Incidents online" value={metrics.active} />
                <InlineMetricStat tone="sky" label="Cameras online" value={metrics.cameras} />
                <InlineMetricStat tone="green" label="Mapped scenes" value={metrics.mapped} />
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

function HeroSignalCard({ label, value }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/45 px-3 py-3 backdrop-blur">
      <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">{label}</div>
      <div className="mt-2 truncate text-sm font-medium text-white">{value}</div>
    </div>
  );
}

function HeroDetailRow({ label, value, tone }) {
  const toneClass =
    tone === "green"
      ? "bg-emerald-400"
      : tone === "warning"
        ? "bg-orange-400"
        : tone === "sky"
          ? "bg-cyan-400"
          : "bg-sky-400";

  return (
    <div className="hero-detail-row">
      <div className="flex items-center gap-3">
        <span className={`hero-detail-dot ${toneClass}`} />
        <span className="text-sm text-slate-400">{label}</span>
      </div>
      <span className="max-w-[55%] truncate text-sm font-semibold text-white">{value}</span>
    </div>
  );
}

function InlineMetricStat({ tone, label, value }) {
  const toneClass =
    tone === "green"
      ? "text-emerald-200 shadow-[0_0_22px_rgba(16,185,129,0.12)]"
      : tone === "warning"
        ? "text-orange-200 shadow-[0_0_22px_rgba(249,115,22,0.10)]"
        : tone === "critical"
          ? "text-red-200 shadow-[0_0_22px_rgba(239,68,68,0.10)]"
          : tone === "sky"
            ? "text-cyan-200 shadow-[0_0_22px_rgba(34,211,238,0.10)]"
            : "text-sky-200 shadow-[0_0_22px_rgba(56,189,248,0.10)]";

  return (
    <div className={`inline-flex items-center gap-3 rounded-full bg-white/[0.04] px-4 py-2 ring-1 ring-white/10 ${toneClass}`}>
      <span className="text-[11px] uppercase tracking-[0.18em] text-slate-400">{label}</span>
      <span className="h-1 w-1 rounded-full bg-current opacity-70" />
      <span className="text-sm font-semibold text-white">{value}</span>
    </div>
  );
}

function FlowStep({ active, label, detail, time }) {
  return (
    <div className={`flow-step ${active ? "flow-step--active" : ""}`}>
      <span className={`flow-step-dot ${active ? "flow-step-dot--active" : ""}`} />
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <div className="text-sm font-medium text-white">{label}</div>
          <div className="text-xs font-medium text-slate-500">{time}</div>
        </div>
        <div className="mt-1 text-sm text-slate-400">{detail}</div>
      </div>
    </div>
  );
}

function RoutingNode({ label, tone }) {
  const toneClass =
    tone === "green"
      ? "text-emerald-200"
      : tone === "emerald"
        ? "text-emerald-100"
        : tone === "sky"
          ? "text-cyan-200"
          : "text-sky-200";
  return (
    <div className={`routing-node ${toneClass}`}>
      <span className="routing-node-dot" />
      <span>{label}</span>
    </div>
  );
}

function StatusRow({ label, value, tone }) {
  const toneClass =
    tone === "green"
      ? "bg-emerald-400"
      : tone === "sky"
        ? "bg-cyan-400"
        : "bg-sky-400";
  return (
    <div className="status-row">
      <div className="flex items-center gap-3">
        <span className={`status-row-dot ${toneClass}`} />
        <span className="text-sm text-slate-300">{label}</span>
      </div>
      <span className="text-sm font-semibold text-white">{value}</span>
    </div>
  );
}

function ActivityTickerItem({ text, tone }) {
  const toneClass =
    tone === "green"
      ? "bg-emerald-400"
      : tone === "sky"
        ? "bg-cyan-400"
        : "bg-sky-400";

  return (
    <div className="activity-ticker-item">
      <span className={`activity-ticker-dot ${toneClass}`} />
      <span className="text-sm text-slate-300">{text}</span>
    </div>
  );
}

function WorkflowStep({ active, label }) {
  return (
    <div className={`flex items-center gap-3 rounded-2xl border px-3 py-3 text-sm ${active ? "border-white/10 bg-white/[0.04] text-slate-200" : "border-white/6 bg-transparent text-slate-500"}`}>
      <span className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${active ? "bg-sky-500/15 text-sky-200 ring-1 ring-sky-500/20" : "bg-white/5 text-slate-500"}`}>
        {active ? "✓" : "•"}
      </span>
      {label}
    </div>
  );
}

function heroSeverityClass(label) {
  if (label === "critical") {
    return "bg-red-500/15 text-red-200 ring-1 ring-red-400/20";
  }
  if (label === "high") {
    return "bg-orange-500/15 text-orange-200 ring-1 ring-orange-400/20";
  }
  if (label === "moderate") {
    return "bg-amber-500/15 text-amber-200 ring-1 ring-amber-400/20";
  }
  if (label === "low") {
    return "bg-yellow-500/15 text-yellow-200 ring-1 ring-yellow-400/20";
  }
  return "bg-slate-500/15 text-slate-200 ring-1 ring-white/10";
}

function DashboardPage({ latestMappedIncident, latestAccident, activeAdmin, metrics, incidents, onDeleteIncident }) {
  return (
    <>
      <MapPanel incident={latestMappedIncident} />

      <section className="grid gap-4 lg:grid-cols-3">
        <AnalyticsCard
          icon={AlertTriangle}
          title="Recent severity"
          value={latestAccident ? latestAccident.severity.label : "Clear"}
          detail={latestAccident ? `Confidence ${Math.round((latestAccident.detection.confidence || 0) * 100)}%` : "No verified incidents yet"}
          tone={latestAccident ? latestAccident.severity.label : "clear"}
        />
        <AnalyticsCard
          icon={Camera}
          title="Registered cameras"
          value={metrics.cameras}
          detail="Source registry loaded for automatic location resolution."
          tone="neutral"
        />
        <AnalyticsCard
          icon={Users}
          title="Admin contact"
          value={activeAdmin ? activeAdmin.name || "Configured" : "Not set"}
          detail={activeAdmin ? activeAdmin.phone || activeAdmin.email || "Ready for alerts" : "No admin routing profile configured"}
          tone="neutral"
        />
      </section>

      <section className="rounded-[28px] border border-white/10 bg-[#0d1726] p-5 shadow-[0_20px_48px_rgba(2,8,23,0.28)] sm:p-6">
        <SectionHeading title="Current operating scene" description="Keep one active evidence snapshot and mapped location in focus. Use Incidents for full case-by-case review." />
        <div className="mt-5">
          {latestAccident ? (
            <DashboardSceneSummary incident={latestAccident} />
          ) : (
            <EmptyState text="No verified incident is active yet." />
          )}
        </div>
      </section>
    </>
  );
}

function IncidentsPage({
  incidents,
  cameraSources,
  selectedFile,
  selectedSourceId,
  setSelectedSourceId,
  uploading,
  uploadInputKey,
  onAnalyze,
  onDeleteIncident,
  onFileChange,
  onVideoPlaybackComplete,
}) {
  const videoSelected = isVideoFile(selectedFile);
  const intakeReady = Boolean(selectedFile?.file && selectedSourceId);

  return (
    <>
      <section className="rounded-[28px] border border-white/10 bg-[#0d1726] p-5 shadow-[0_20px_48px_rgba(2,8,23,0.28)] sm:p-6">
        <SectionHeading title="Incident intake" description="Upload image or video evidence, attach a known camera source, and trigger AI review." />

        <form className="mt-6 space-y-5" onSubmit={onAnalyze}>
          <div className="rounded-[24px] border border-dashed border-white/10 bg-[#08111d] p-5 transition hover:border-sky-400/30 hover:bg-[#0a1422]">
            <label className="block cursor-pointer">
              <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/5 text-sky-200 shadow-sm ring-1 ring-white/10">
                  <Upload size={20} />
                </div>
                <div>
                  <div className="text-base font-medium text-white">Upload accident image or video</div>
                  <div className="mt-1 text-sm text-slate-400">Drag and drop or browse local evidence for analysis.</div>
                </div>
              </div>
              <input key={uploadInputKey} accept="image/*,video/*" className="mt-4 block w-full text-sm text-slate-300 file:mr-4 file:rounded-full file:border-0 file:bg-sky-500 file:px-4 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-sky-400" name="image" required type="file" onChange={onFileChange} />
            </label>
          </div>

          <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-300">Camera source</label>
              <select
                className="w-full rounded-2xl border border-white/10 bg-[#08111d] px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/40 focus:ring-4 focus:ring-sky-400/10"
                name="source_id"
                required
                value={selectedSourceId}
                onChange={(event) => setSelectedSourceId(event.target.value)}
              >
                <option value="">Select a known camera source</option>
                {cameraSources.map((source) => (
                  <option key={source.source_id} value={source.source_id}>
                    {source.source_id} - {source.source_name}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-end">
              {videoSelected ? (
                <div
                  className={`inline-flex w-full items-center justify-center rounded-2xl border px-5 py-3 text-sm font-medium ${
                    intakeReady ? "border-sky-400/20 bg-sky-400/10 text-sky-200" : "border-amber-400/20 bg-amber-400/10 text-amber-200"
                  }`}
                >
                  {uploading
                    ? "Scanning video automatically..."
                    : intakeReady
                      ? "Video analysis runs automatically"
                      : "Select file and camera source first"}
                </div>
              ) : (
                <button
                  className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-sky-500 px-5 py-3 text-sm font-medium text-white transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:bg-slate-500"
                  disabled={uploading || !intakeReady}
                  type="submit"
                >
                  <Upload size={16} />
                  {uploading ? "Analyzing incident..." : "Analyze incident"}
                </button>
              )}
            </div>
          </div>
        </form>

        {selectedFile ? <PreviewCard file={selectedFile} onVideoEnded={onVideoPlaybackComplete} uploading={uploading} /> : null}
      </section>

      <section className="rounded-[28px] border border-white/10 bg-[#0d1726] p-5 shadow-[0_20px_48px_rgba(2,8,23,0.28)] sm:p-6">
        <SectionHeading title="Incident review feed" description="Latest uploaded cases appear here with severity, confidence, location links, and alert status." />
        <div className="mt-5 space-y-4">
          {incidents.length ? (
            incidents.map((incident) => <IncidentCard key={incident.id} incident={incident} onDelete={onDeleteIncident} />)
          ) : (
            <EmptyState text="No processed incidents are available yet." />
          )}
        </div>
      </section>
    </>
  );
}

function CamerasPage({ cameraSources }) {
  return (
    <section className="rounded-[28px] border border-white/10 bg-[#0d1726] p-5 shadow-[0_20px_48px_rgba(2,8,23,0.28)] sm:p-6">
      <SectionHeading title="Camera registry" description="Registered source IDs resolve location automatically when evidence has no embedded GPS metadata." />
      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {cameraSources.length ? (
          cameraSources.slice(0, 24).map((source) => (
            <div key={source.source_id} className="camera-registry-card rounded-2xl border border-white/10 bg-white/[0.03] p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm font-semibold text-white">{source.source_id}</div>
                <span className="inline-flex items-center gap-2 rounded-full bg-emerald-400/10 px-2.5 py-1 text-[11px] font-medium text-emerald-300">
                  <span className="status-pulse-dot bg-emerald-400" />
                  Online
                </span>
              </div>
              <div className="mt-1 text-sm text-slate-400">{source.source_name}</div>
              <div className="mt-3 text-xs text-slate-500">
                {source.latitude}, {source.longitude}
              </div>
            </div>
          ))
        ) : (
          <EmptyState text="No registered camera sources are loaded." />
        )}
      </div>
    </section>
  );
}

function MapPage({ latestMappedIncident }) {
  return <MapPanel incident={latestMappedIncident} />;
}

function AdminPage({ activeAdmin, contactForm, setContactForm, onSubmit, onDelete }) {
  return (
    <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
      <section className="rounded-[28px] border border-white/10 bg-[#0d1726] p-5 shadow-[0_20px_48px_rgba(2,8,23,0.28)] sm:p-6">
        <SectionHeading title="Admin contact settings" description="Configure the single alert-routing contact used for verified incident notifications." />
        <form className="mt-6 space-y-4" onSubmit={onSubmit}>
          <Input label="Name" value={contactForm.name} onChange={(value) => setContactForm((current) => ({ ...current, name: value }))} />
          <Input label="Phone number" value={contactForm.phone} onChange={(value) => setContactForm((current) => ({ ...current, phone: value }))} />
          <Input label="Email" type="email" value={contactForm.email} onChange={(value) => setContactForm((current) => ({ ...current, email: value }))} />
          <Input label="Role" value={contactForm.relation} onChange={(value) => setContactForm((current) => ({ ...current, relation: value }))} />

          <button className="inline-flex items-center justify-center rounded-2xl bg-sky-500 px-5 py-3 text-sm font-medium text-white transition hover:bg-sky-400" type="submit">
            Save admin contact
          </button>
        </form>
      </section>

      <section className="rounded-[28px] border border-white/10 bg-[#0d1726] p-5 shadow-[0_20px_48px_rgba(2,8,23,0.28)] sm:p-6">
        <SectionHeading title="Active routing profile" description="Accident alerts are routed only to the configured admin contact." />

        {activeAdmin ? (
          <div className="mt-6 rounded-[24px] border border-white/10 bg-white/[0.03] p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-lg font-semibold text-white">{activeAdmin.name || "Configured admin"}</div>
                <div className="mt-1 text-sm text-slate-400">{activeAdmin.relation || "Alert recipient"}</div>
              </div>
              <span className="rounded-full bg-emerald-400/10 px-3 py-1 text-xs font-semibold text-emerald-300">Active</span>
            </div>

            <div className="mt-5 space-y-2 text-sm text-slate-300">
              {activeAdmin.phone ? <div>{activeAdmin.phone}</div> : null}
              {activeAdmin.email ? <div>{activeAdmin.email}</div> : null}
            </div>

            <button
              className="mt-5 inline-flex items-center gap-2 rounded-2xl border border-red-500/20 px-4 py-2 text-sm font-medium text-red-300 transition hover:bg-red-500/10"
              type="button"
              onClick={() => onDelete(activeAdmin.id)}
            >
              <Trash2 size={15} />
              Delete admin
            </button>
          </div>
        ) : (
          <EmptyState text="No admin contact is configured yet." />
        )}
      </section>
    </div>
  );
}

function MapPanel({ incident }) {
  return (
    <section className="rounded-[30px] border border-white/10 bg-[#0d1726] p-5 shadow-[0_20px_48px_rgba(2,8,23,0.28)] sm:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <SectionHeading title="Live location" description="Most recent mapped incident location with resolved street context and scene position." />
        {incident?.location?.source ? <div className="text-sm text-slate-400">{incident.location.source}</div> : null}
      </div>

      <div className="mt-5 overflow-hidden rounded-[26px] border border-white/10 bg-[#08111d]">
        {incident?.location?.latitude && incident?.location?.longitude ? (
          <MapScene incident={incident} />
        ) : (
          <div className="flex h-[460px] items-center justify-center px-6 text-center text-sm text-slate-500">
            No mapped incident is available yet. Upload evidence with GPS metadata or choose a registered camera source.
          </div>
        )}
      </div>

      <div className="mt-4 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-slate-300">
        {incident?.location?.address || "Location details will appear here once the system resolves a mapped incident."}
      </div>
    </section>
  );
}

function SectionHeading({ title, description }) {
  return (
    <div>
      <h2 className="text-2xl font-semibold tracking-tight text-white">{title}</h2>
      {description ? <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">{description}</p> : null}
    </div>
  );
}

function HeroMetric({ title, value, tone }) {
  const toneClass =
    tone === "green"
      ? "text-emerald-200"
      : tone === "blue"
        ? "text-sky-200"
        : tone === "critical"
          ? "text-red-200"
          : tone === "warning"
            ? "text-orange-200"
            : "text-slate-200";

  return (
    <div className="hero-metric-inline">
      <span className={`hero-metric-inline-label ${toneClass}`}>{title}</span>
      <span className="hero-metric-inline-separator">•</span>
      <span className="hero-metric-inline-value">{value}</span>
    </div>
  );
}

function TopNavButton({ active, icon: Icon, label, onClick }) {
  return (
    <button
      className={`inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-medium transition ${
        active ? "bg-sky-500 text-white shadow-[0_14px_32px_rgba(14,165,233,0.28)]" : "text-slate-300 hover:bg-white/6 hover:text-white"
      }`}
      type="button"
      onClick={onClick}
    >
      <Icon size={16} />
      {label}
    </button>
  );
}

function AnalyticsCard({ icon: Icon, title, value, detail, tone }) {
  const toneAccent =
    tone === "critical"
      ? "analytics-card analytics-card--critical"
      : tone === "high"
        ? "analytics-card analytics-card--high"
        : tone === "moderate"
          ? "analytics-card analytics-card--moderate"
          : tone === "low"
            ? "analytics-card analytics-card--low"
            : tone === "clear"
              ? "analytics-card analytics-card--clear"
              : "analytics-card";

  return (
    <div className={`rounded-[26px] border bg-[#0d1726] p-5 shadow-[0_18px_38px_rgba(2,8,23,0.24)] ${toneAccent}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium text-slate-300">
          <span className={`h-2.5 w-2.5 rounded-full ${analyticsToneDot(tone)}`} />
          {title}
        </div>
        <Icon size={18} className="text-slate-500" />
      </div>
      <div className="mt-3 text-3xl font-semibold tracking-tight text-white">{value}</div>
      <div className="mt-2 text-sm leading-6 text-slate-400">{detail}</div>
    </div>
  );
}

function analyticsToneDot(tone) {
  if (tone === "critical") return "bg-red-400 shadow-[0_0_16px_rgba(248,113,113,0.55)]";
  if (tone === "high") return "bg-orange-400 shadow-[0_0_16px_rgba(251,146,60,0.48)]";
  if (tone === "moderate") return "bg-amber-400 shadow-[0_0_14px_rgba(251,191,36,0.42)]";
  if (tone === "low") return "bg-yellow-300 shadow-[0_0_12px_rgba(253,224,71,0.36)]";
  if (tone === "clear") return "bg-emerald-400 shadow-[0_0_16px_rgba(52,211,153,0.42)]";
  return "bg-sky-400 shadow-[0_0_16px_rgba(56,189,248,0.42)]";
}

function Input({ label, type = "text", value, onChange }) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm font-medium text-slate-300">{label}</span>
      <input
        className="w-full rounded-2xl border border-white/10 bg-[#08111d] px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/40 focus:ring-4 focus:ring-sky-400/10"
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function EmptyState({ text }) {
  return <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.03] px-4 py-6 text-sm text-slate-500">{text}</div>;
}

function DashboardSceneSummary({ incident }) {
  const isAccident = incident.detection.accident_detected;
  const confidencePercent = Math.round((incident.detection.confidence || 0) * 100);
  const snapshotUrl = incident.image_url ? `${API_ORIGIN}${incident.image_url}` : "";
  const locationLabel = incident.location?.address || incident.location?.source || "Location unresolved";

  return (
    <div className="grid gap-5 lg:grid-cols-[280px_1fr]">
      <div className="overflow-hidden rounded-[24px] border border-white/10 bg-slate-950/40">
        <div className="aspect-[4/3] w-full overflow-hidden">
          {snapshotUrl ? (
            <img alt="Incident snapshot" className="h-full w-full object-cover" src={snapshotUrl} />
          ) : (
            <div className="flex h-full items-center justify-center text-xs text-slate-500">No snapshot</div>
          )}
        </div>
        <div className="border-t border-white/10 px-4 py-3 text-sm text-slate-400">
          {incident.location?.source || "Unresolved source"}
        </div>
      </div>

      <div className="rounded-[24px] border border-white/10 bg-white/[0.03] p-5">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ${
              isAccident ? "bg-red-400/10 text-red-200 ring-1 ring-red-400/20" : "bg-slate-400/10 text-slate-200 ring-1 ring-white/10"
            }`}
          >
            <span className={`h-2 w-2 rounded-full ${isAccident ? "bg-red-400" : "bg-slate-300"}`} />
            {isAccident ? "Accident detected" : "No accident"}
          </span>
          <span className="inline-flex items-center rounded-full bg-orange-400/10 px-3 py-1 text-xs font-medium capitalize text-orange-200 ring-1 ring-orange-400/20">
            Severity {incident.severity?.label || "low"}
          </span>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <SceneMetaItem label="Confidence" value={`${confidencePercent}%`} />
          <SceneMetaItem label="Captured" value={formatTimestamp(incident.created_at)} />
          <SceneMetaItem label="Source media" value={incident.source_media || "image"} />
        </div>

        <div className="mt-5 rounded-2xl border border-white/10 bg-slate-950/35 px-4 py-4">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Mapped location</div>
          <div className="mt-2 text-sm leading-6 text-slate-300">{locationLabel}</div>
        </div>
      </div>
    </div>
  );
}

function SceneMetaItem({ label, value }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/35 px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">{label}</div>
      <div className="mt-2 text-sm font-medium text-white">{value}</div>
    </div>
  );
}

function PreviewCard({ file, onVideoEnded, uploading }) {
  const isVideo = isVideoFile(file);
  return (
    <div className="mt-6 rounded-[24px] border border-white/10 bg-[#08111d] p-4">
      <div className="text-sm font-medium text-slate-300">Upload preview</div>
      <div className="mt-3 overflow-hidden rounded-[20px] border border-white/10 bg-slate-950">
        {isVideo ? (
          <video className="max-h-[320px] w-full bg-slate-950 object-contain" controls preload="metadata" src={file.url} onEnded={onVideoEnded} />
        ) : (
          <img alt={file.name} className="max-h-[320px] w-full object-cover" src={file.url} />
        )}
      </div>
      <div className="mt-3 text-sm text-slate-400">
        {isVideo
          ? "Select a camera source, then play the video normally. When playback ends, the system will analyze the full clip automatically."
          : "Select a camera source, then run analysis on the uploaded image."}
      </div>
      {isVideo ? (
        <div className="mt-3 rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-slate-300">
          {file.analysisState === "running"
            ? "Video analysis is running in the background."
            : file.analysisState === "complete"
              ? "Video analysis finished. Check the incident feed for the captured moment."
              : file.analysisState === "error"
                ? "Video analysis failed. Refresh and try the clip again."
                : uploading
                  ? "Video analysis is starting."
                  : "Playback completion will trigger automatic analysis."}
        </div>
      ) : null}
    </div>
  );
}

function MapScene({ incident }) {
  const position = [incident.location.latitude, incident.location.longitude];

  return (
    <MapContainer
      center={position}
      className="accisense-map h-[460px] w-full"
      dragging={true}
      doubleClickZoom={true}
      scrollWheelZoom={false}
      touchZoom={true}
      whenReady={(event) => {
        const map = event.target;
        map.dragging.enable();
        map.scrollWheelZoom.disable();
        map.doubleClickZoom.enable();
        map.touchZoom.enable();
      }}
      zoom={15}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; CARTO'
        url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
      />
      <Marker icon={liveLocationIcon} position={position}>
        <Popup>
          <div className="space-y-1">
            <div className="font-semibold">{incident.location.address || "Accident location"}</div>
            <div className="text-sm text-slate-500">{incident.location.source || "Resolved location"}</div>
          </div>
        </Popup>
        <Tooltip className="accident-live-tooltip" direction="top" interactive={false} offset={[0, -16]} opacity={1} permanent>
          Accident location
        </Tooltip>
      </Marker>
    </MapContainer>
  );
}

function IncidentCard({ incident, onDelete }) {
  const snapshotUrl = incident.image_url ? `${API_ORIGIN}${incident.image_url}` : "";
  const mapsUrl = incident.location?.google_maps_url || incident.location?.osm_url || "";
  const isAccident = incident.detection.accident_detected;
  const confidencePercent = Math.round((incident.detection.confidence || 0) * 100);
  const aiReasoning = summarizeAiReasoning(incident);

  return (
    <article className={`overflow-hidden rounded-[28px] border shadow-[0_18px_38px_rgba(2,8,23,0.26)] ${isAccident ? "border-red-500/20 bg-[#0f1726]" : "border-white/10 bg-[#0d1726]"}`}>
      <div className={`h-1 w-full ${isAccident ? "bg-gradient-to-r from-red-500/0 via-red-400 to-red-500/0" : "bg-gradient-to-r from-slate-500/0 via-slate-600/30 to-slate-500/0"}`} />
      <div className="grid gap-5 p-4 sm:p-5 lg:grid-cols-[260px_1fr]">
        <div>
          <div className="overflow-hidden rounded-[22px] border border-white/10 bg-[#08111d]">
            {snapshotUrl ? (
              <img alt="Incident snapshot" className="h-[220px] w-full object-cover" src={snapshotUrl} />
            ) : (
              <div className="flex h-[220px] items-center justify-center text-sm text-slate-500">No incident snapshot</div>
            )}
          </div>
          <div className="mt-3 text-sm text-slate-400">Source media: {incident.media_type}</div>
        </div>

        <div className="min-w-0">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex flex-wrap gap-2">
              <StatusChip tone={isAccident ? "critical" : "neutral"} icon={AlertTriangle} text={isAccident ? "Accident detected" : "No accident"} />
              {isAccident ? <StatusChip tone={incident.severity.label} text={`Severity: ${incident.severity.label}`} /> : null}
              {incident.location?.source ? <StatusChip tone="info" text={incident.location.source} icon={MapPinned} /> : null}
            </div>

            <div className="flex items-center gap-3">
              <div className="text-right">
                <div className="text-sm text-slate-300">{formatTimestamp(incident.created_at)}</div>
                <div className="mt-1 text-xs text-slate-500">{formatRelativeTime(incident.created_at)}</div>
              </div>
              <button className="inline-flex items-center gap-2 rounded-full border border-red-500/20 px-3 py-2 text-sm font-medium text-red-300 transition hover:bg-red-500/10" type="button" onClick={() => onDelete(incident.id)}>
                <Trash2 size={15} />
                Delete
              </button>
            </div>
          </div>

          <div className="mt-4 text-sm text-slate-300">
            Confidence {confidencePercent}% | Severity score {incident.severity.score}
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_280px]">
            <div className="rounded-[22px] border border-sky-500/15 bg-sky-500/[0.06] p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm font-semibold text-sky-100">AI confidence</div>
                <div className="text-sm font-medium text-sky-200">{confidencePercent}%</div>
              </div>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-[#07111f]">
                <div className="confidence-meter h-full rounded-full bg-[linear-gradient(90deg,#38bdf8,#60a5fa,#93c5fd)]" style={{ width: `${confidencePercent}%` }} />
              </div>
              <div className="mt-3 text-sm leading-6 text-slate-400">{aiReasoning}</div>
            </div>

            <div className="rounded-[22px] border border-white/10 bg-white/[0.03] p-4">
              <div className="text-sm font-semibold text-white">AI reasoning</div>
              <div className="mt-3 space-y-2">
                {getReasoningLines(incident).map((line, index) => (
                  <div key={`${incident.id}-reason-${index}`} className="flex items-start gap-2 text-sm text-slate-400">
                    <span className="mt-1 h-1.5 w-1.5 rounded-full bg-sky-400" />
                    <span>{line}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {isAccident ? (
            <>
              <div className="mt-4 grid items-start gap-4 lg:grid-cols-2">
                <PlaceBlock icon={Hospital} title="Nearest hospitals" items={incident.location?.nearest_hospitals || []} emptyText="No nearby hospitals found." />
                <PlaceBlock icon={Phone} title="Nearest police stations" items={incident.location?.nearest_police_stations || []} emptyText="No nearby police stations found." />
              </div>

              <div className="mt-5 flex flex-wrap gap-2">
                {mapsUrl ? <ActionLink href={mapsUrl} label="Open location" /> : null}
                {snapshotUrl ? <ActionLink href={snapshotUrl} label="Open snapshot" /> : null}
              </div>

              {incident.notification_summary?.sms_results?.length ? (
                <div className="mt-4 space-y-2">
                  {incident.notification_summary.sms_results.map((result) =>
                    result.error ? (
                      <Notice key={`${result.phone}-error`} tone="warning" text={`SMS failed for ${result.phone}: ${JSON.stringify(result.error)}`} />
                    ) : (
                      <Notice key={`${result.phone}-ok`} tone="success" text={`Twilio ${result.status || "queued"} SMS to ${result.phone}${result.sid ? ` (SID: ${result.sid})` : ""}.`} />
                    )
                  )}
                </div>
              ) : null}

              {incident.notification_summary?.email_sent_to?.length ? (
                <Notice tone="success" text={`Email sent to ${incident.notification_summary.email_sent_to.join(", ")}.`} />
              ) : null}

              {incident.notification_summary?.email_errors?.length
                ? incident.notification_summary.email_errors.map((entry) => (
                    <Notice key={`${entry.email}-email-error`} tone="warning" text={`Email failed for ${entry.email}: ${entry.error}`} />
                  ))
                : null}
            </>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function PlaceBlock({ icon: Icon, title, items, emptyText }) {
  return (
    <div className={`rounded-[22px] border border-white/10 bg-white/[0.03] p-4 ${items.length ? "" : "min-h-0"}`}>
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
        <Icon size={16} className="text-slate-400" />
        {title}
      </div>
      <div className={`mt-3 ${items.length ? "space-y-3" : ""}`}>
        {items.length ? (
          items.slice(0, 3).map((item, index) => (
            <div key={`${item.name}-${index}`}>
              <div className="text-sm font-medium text-white">{item.name}</div>
              <div className="text-sm leading-6 text-slate-400">{item.address || "Address unavailable"}</div>
            </div>
          ))
        ) : (
          <div className="rounded-2xl bg-white/[0.02] px-3 py-3 text-sm text-slate-500">{emptyText}</div>
        )}
      </div>
    </div>
  );
}

function StatusChip({ tone, text, icon: Icon }) {
  const toneClass =
    tone === "critical"
      ? "bg-red-500/10 text-red-200 ring-1 ring-red-500/20"
      : tone === "high"
        ? "bg-orange-500/10 text-orange-200 ring-1 ring-orange-500/20"
        : tone === "moderate"
          ? "bg-amber-500/10 text-amber-200 ring-1 ring-amber-500/20"
          : tone === "low"
            ? "bg-yellow-500/10 text-yellow-200 ring-1 ring-yellow-500/20"
            : tone === "info"
              ? "bg-sky-500/10 text-sky-200 ring-1 ring-sky-500/20"
              : "bg-white/8 text-slate-300 ring-1 ring-white/10";

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold ${toneClass}`}>
      {Icon ? <Icon size={13} /> : null}
      {text}
    </span>
  );
}

function Notice({ tone, text }) {
  const toneClass = tone === "success" ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-200" : "border-amber-500/20 bg-amber-500/10 text-amber-200";
  return <div className={`mt-3 rounded-2xl border px-4 py-3 text-sm ${toneClass}`}>{text}</div>;
}

function ActionLink({ href, label }) {
  return (
    <a className="inline-flex items-center rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-sky-400/30 hover:bg-sky-500/10 hover:text-sky-100" href={href} rel="noreferrer" target="_blank">
      {label}
    </a>
  );
}

function getPageFromHash() {
  const page = window.location.hash.replace("#", "");
  return NAV_ITEMS.some((item) => item.key === page) ? page : "dashboard";
}

function formatTimestamp(value) {
  if (!value) {
    return "Timestamp unavailable";
  }

  try {
    return new Intl.DateTimeFormat("en-IN", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function formatLiveClock(value) {
  return new Intl.DateTimeFormat("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(value);
}

function formatRelativeTime(value) {
  if (!value) {
    return "Waiting for update";
  }

  const diff = Date.now() - new Date(value).getTime();
  if (Number.isNaN(diff)) {
    return "Waiting for update";
  }

  const minutes = Math.round(diff / 60000);
  if (minutes <= 1) {
    return "Updated just now";
  }
  if (minutes < 60) {
    return `Updated ${minutes} min ago`;
  }
  const hours = Math.round(minutes / 60);
  return `Updated ${hours} hr ago`;
}

function formatRelativeStageTime(value, offsetMinutes = 0) {
  if (!value) {
    return "--:--";
  }

  const base = new Date(value);
  if (Number.isNaN(base.getTime())) {
    return "--:--";
  }

  base.setMinutes(base.getMinutes() + offsetMinutes);
  return new Intl.DateTimeFormat("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(base);
}

function getDispatchStateLabel(incident) {
  if (!incident) {
    return "No verified incident yet";
  }

  const summary = incident.notification_summary;
  if (!summary) {
    return "No alert record yet";
  }

  const smsOk = summary.sms_results?.some((result) => !result.error);
  const emailOk = summary.email_sent_to?.length;

  if (smsOk || emailOk) {
    return "Alerts sent";
  }

  const smsFail = summary.sms_results?.some((result) => result.error);
  const emailFail = summary.email_errors?.length;

  if (smsFail || emailFail) {
    return "Alert delivery issue";
  }

  return "Dispatch prepared";
}

function isVideoFile(file) {
  if (!file) {
    return false;
  }

  if (file.type?.startsWith("video/")) {
    return true;
  }

  return /\.(mp4|avi|mov|mkv|webm)$/i.test(file.name || "");
}

function summarizeAiReasoning(incident) {
  if (!incident.detection?.accident_detected) {
    return "The system downgraded this scene after applying conservative roadway and static-scene safety checks.";
  }

  if (incident.severity?.label === "critical") {
    return "The system found severe damage or extreme emergency evidence that crossed the critical-response threshold.";
  }

  if (incident.severity?.label === "high") {
    return "The classifier sees a strong crash signature and elevated impact evidence, but not enough for the critical tier.";
  }

  if (incident.severity?.label === "moderate") {
    return "The model identified a visible accident with contained impact evidence and limited extreme-risk signals.";
  }

  return "The detector triggered with low overall severity evidence and no extreme emergency markers.";
}

function getReasoningLines(incident) {
  const evidence = incident.detection?.evidence || [];
  const rationale = incident.severity?.rationale || [];
  const lines = [...evidence, ...rationale].filter(Boolean).slice(0, 3);
  return lines.length ? lines : ["Model review completed using the current accident, severity, and location heuristics."];
}

