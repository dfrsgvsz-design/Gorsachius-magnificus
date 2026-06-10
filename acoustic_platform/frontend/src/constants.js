import {
  Activity,
  AudioWaveform,
  BarChart3,
  BookOpen,
  Calendar,
  Crosshair,
  Eye,
  LayoutDashboard,
  Mic,
  Monitor,
  Radio,
  Settings,
  Shield,
  Waves,
} from "lucide-react";

export const APP_COPY = {
  en: {
    appName: "Ecoacoustic Index Platform",
    appNameMobile: "EcoAcoustic",
    appSubtitle:
      "Soundscape analysis and ecosystem health monitoring for conservation research",
  },
  zh: {
    appName: "声景生态指数平台",
    appNameMobile: "声景指数",
    appSubtitle: "面向保护研究的声景分析与生态系统健康监测",
  },
};

export const DEFAULT_TAB_ID = "dashboard";

export const TABS = [
  { id: "dashboard", labelKey: "tabs.dashboard", icon: LayoutDashboard },
  { id: "soundscape", labelKey: "tabs.soundscape", icon: Waves },
  { id: "analyze", labelKey: "tabs.analyze", icon: Mic },
  { id: "verify", labelKey: "tabs.verify", icon: Shield },
  { id: "monitor", labelKey: "tabs.monitor", icon: Activity },
  { id: "devices", labelKey: "tabs.devices", icon: Radio },
  { id: "embeddings", labelKey: "tabs.embeddings", icon: Eye },
  { id: "phenology", labelKey: "tabs.phenology", icon: Calendar },
  { id: "occupancy", labelKey: "tabs.occupancy", icon: BarChart3 },
  { id: "fewshot", labelKey: "tabs.fewshot", icon: Crosshair },
  { id: "settings", labelKey: "tabs.settings", icon: Settings },
  { id: "about", labelKey: "tabs.about", icon: BookOpen },
];

export const NAV_GROUPS = [
  {
    id: "overview",
    label: { en: "Overview", zh: "概览" },
    icon: LayoutDashboard,
    tabs: ["dashboard"],
  },
  {
    id: "acoustic-core",
    label: { en: "Acoustic Analysis", zh: "声学分析" },
    icon: AudioWaveform,
    tabs: ["soundscape", "analyze", "verify"],
  },
  {
    id: "monitoring",
    label: { en: "Monitoring", zh: "监测" },
    icon: Monitor,
    tabs: ["monitor", "devices"],
  },
  {
    id: "advanced",
    label: { en: "Advanced", zh: "进阶" },
    icon: Eye,
    tabs: ["embeddings", "phenology", "occupancy", "fewshot"],
  },
  {
    id: "system",
    label: { en: "System", zh: "系统" },
    icon: Settings,
    tabs: ["settings", "about"],
  },
];

export const MOBILE_PRIMARY_TAB_IDS = [
  "dashboard",
  "soundscape",
  "analyze",
  "monitor",
];
export const MOBILE_MORE_TAB_IDS = TABS.map((tab) => tab.id).filter(
  (id) => !MOBILE_PRIMARY_TAB_IDS.includes(id)
);

export const TAB_SUMMARIES = {
  en: {
    dashboard:
      "Ecosystem health overview with acoustic index summaries and system status.",
    soundscape:
      "Compute and visualize ecoacoustic indices — ACI, NDSI, ADI, BIO, entropy, and evenness.",
    analyze:
      "Upload audio recordings for AI-powered species detection and classification.",
    verify:
      "Review, confirm, or reject AI detections before downstream analysis.",
    monitor:
      "Real-time monitoring sessions and live acoustic data streams.",
    devices:
      "Manage field recording devices — AudioMoth, Song Meter, and custom units.",
    embeddings:
      "Explore acoustic embedding space, similarity patterns, and novelty detection.",
    phenology:
      "Seasonal vocal activity patterns, onset trends, and phenological shifts.",
    occupancy:
      "Estimate true species occupancy corrected for imperfect detection probability.",
    fewshot:
      "Create custom species detectors from 1–5 reference recordings.",
    settings: "Platform configuration, API keys, and runtime health checks.",
    about: "Research context, methodology, and platform documentation.",
  },
  zh: {
    dashboard: "声景生态系统健康概览、声学指数汇总与系统状态。",
    soundscape:
      "计算与可视化声景生态指数——ACI、NDSI、ADI、BIO、熵和均匀度。",
    analyze: "上传音频录音进行 AI 物种检测与分类。",
    verify: "在下游分析前审核、确认或否决 AI 检测结果。",
    monitor: "实时监测会话与声学数据流。",
    devices: "管理野外录音设备——AudioMoth、Song Meter 等。",
    embeddings: "探索声学嵌入空间、相似性模式和新奇检测。",
    phenology: "季节性发声活动规律、起始趋势和物候漂移分析。",
    occupancy: "校正不完美检测概率后的真实占域概率估计。",
    fewshot: "仅需 1-5 条参考录音即可创建自定义物种检测器。",
    settings: "平台配置、API 密钥和运行健康检查。",
    about: "研究背景、方法论和平台文档。",
  },
};

export const COLORS = {
  carnelian: "#B31B1B",
  darkGray: "#222222",
  lightGray: "#F7F7F7",
  warmGray: "#A2998B",
  seaGray: "#9FAD9F",
  processBlue: "#006699",
  teal: "#0D7377",
  forest: "#2D6A4F",
  chart: [
    "#006699",
    "#0D7377",
    "#2D6A4F",
    "#B31B1B",
    "#A2998B",
    "#4A7C59",
    "#1B4965",
    "#9FAD9F",
    "#D4A373",
    "#5C4033",
  ],
};
