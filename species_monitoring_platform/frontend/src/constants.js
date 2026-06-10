import {
  Activity,
  BookOpen,
  Bug,
  Database,
  FolderOpen,
  Leaf,
  LayoutDashboard,
  MapPin,
  Radio,
  Settings,
  Shield,
} from "lucide-react";

export const APP_COPY = {
  en: {
    appName: "Biodiversity Field Survey Platform",
    appNameMobile: "Field Survey",
    appSubtitle:
      "Offline-first biodiversity surveys for field teams",
    workspace: "Field survey workspace",
    workspaceBody:
      "The primary release shell focuses on Android offline survey execution, reconnection-safe sync, and jurisdiction-ready exports.",
    showDeferredTabs: "More modules",
    hideDeferredTabs: "Hide modules",
    deferredModules: "Secondary modules",
    deferredModulesBody:
      "Keep biodiversity field work primary while acoustic and analysis tools stay available as secondary workspaces.",
  },
  zh: {
    appName: "生物多样性野外调查平台",
    appNameMobile: "野外调查",
    appSubtitle: "面向野外调查团队的离线优先生物多样性调查平台",
    workspace: "野外调查工作台",
    workspaceBody:
      "当前发布主线聚焦 Android 离线调查、断网恢复同步，以及分辖区导出能力。",
    showDeferredTabs: "更多模块",
    hideDeferredTabs: "收起模块",
    deferredModules: "次级模块",
    deferredModulesBody:
      "保持野外调查为主线，声学与分析功能作为次级工作区保留。",
  },
};

export const FIELD_RELEASE_MODE = true;
export const PILOT_MODE = import.meta.env.VITE_PILOT_MODE === "true";
// Field survey is the primary release lane — open the survey workspace by default
// so offline crews land on the actionable shell instead of the overview.
export const DEFAULT_TAB_ID = "fieldops";
export const DEFAULT_SURVEY_MODULE_ID = "terrestrial_vertebrates";

export const SURVEY_MODULES = [
  {
    id: "terrestrial_vertebrates",
    icon: FolderOpen,
    label: { en: "Terrestrial Vertebrates", zh: "陆生脊椎动物" },
    description: {
      en: "Combine bird transects and point counts with mammal trap or net records and amphibian or reptile infrared-camera workflows in one module shell.",
      zh: "将鸟类样线与样点、兽类陷阱或网捕记录，以及两栖爬行动物红外相机流程整合到同一模块壳层中。",
    },
    shellHint: {
      en: "Use one field lane for birds, mammals, amphibians, and reptiles while keeping protocol-specific forms separated inside the module.",
      zh: "在一个野外作业壳层内覆盖鸟类、兽类、两栖类和爬行类，同时保持各协议表单彼此独立。",
    },
    protocols: {
      en: [
        "Bird line transect",
        "Bird point count",
        "Mammal trap or net",
        "Herp infrared camera",
      ],
      zh: ["鸟类样线", "鸟类样点", "兽类网捕或陷阱", "两栖爬行类红外相机"],
    },
  },
  {
    id: "plants",
    icon: Leaf,
    label: { en: "Plants", zh: "植物" },
    description: {
      en: "Keep quadrat and vegetation-transect work in a dedicated shell while the same backend continues to receive the resulting species and effort records.",
      zh: "将样方和植被样带调查放在独立壳层中，同时继续写入同一套后端调查数据。",
    },
    shellHint: {
      en: "This module narrows the shell to quadrat and transect vegetation workflows without exposing backend convergence to field staff.",
      zh: "该模块把前端壳层收敛到样方和样带植被流程，不向野外人员暴露后端汇聚逻辑。",
    },
    protocols: {
      en: ["Plant quadrat", "Plant transect"],
      zh: ["植物样方", "植物样带"],
    },
  },
  {
    id: "insects",
    icon: Bug,
    label: { en: "Insects", zh: "昆虫" },
    description: {
      en: "Reserve a separate shell for insect transect counts so route-linked effort and species records stay isolated from vertebrate and plant surveys.",
      zh: "为昆虫样线计数保留独立模块壳层，使路线相关努力值和物种记录与脊椎动物、植物调查分离。",
    },
    shellHint: {
      en: "The shell stays route-aware for transect counting while still writing into the same unified survey backend behind the scenes.",
      zh: "该模块保持面向样线计数的路线视角，同时继续写入统一的调查后端。",
    },
    protocols: {
      en: ["Insect transect"],
      zh: ["昆虫样线"],
    },
  },
];

export const TABS = [
  { id: "dashboard", labelKey: "tabs.dashboard", icon: LayoutDashboard },
  { id: "fieldops", labelKey: "tabs.fieldops", icon: FolderOpen },
  { id: "species", labelKey: "tabs.species", icon: Database },
  { id: "monitor", labelKey: "tabs.monitor", icon: Activity },
  { id: "verify", labelKey: "tabs.verify", icon: Shield },
  { id: "devices", labelKey: "tabs.devices", icon: Radio },
  { id: "sdm", labelKey: "tabs.sdm", icon: MapPin },
  { id: "settings", labelKey: "tabs.settings", icon: Settings },
  { id: "about", labelKey: "tabs.about", icon: BookOpen },
];

export const NAV_GROUPS = [
  {
    id: "overview",
    label: { en: "Overview", zh: "总览" },
    icon: null,
    tabs: ["dashboard"],
  },
  {
    id: "field-release",
    label: { en: "Field Survey", zh: "野外调查" },
    icon: FolderOpen,
    tabs: ["fieldops", "species"],
  },
  {
    id: "data",
    label: { en: "Data & Review", zh: "数据管理" },
    icon: Shield,
    tabs: ["verify", "monitor"],
  },
  {
    id: "tools",
    label: { en: "Tools", zh: "工具" },
    icon: MapPin,
    tabs: ["sdm", "devices"],
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
  "fieldops",
  "species",
  "monitor",
];
export const MOBILE_MORE_TAB_IDS = TABS.map((tab) => tab.id).filter(
  (id) => !MOBILE_PRIMARY_TAB_IDS.includes(id),
);

export const TAB_SUMMARIES = {
  en: {
    dashboard:
      "Overview of field survey progress, recent observations, and system status at a glance.",
    fieldops:
      "Run offline biodiversity surveys across vertebrate, plant, and insect workflows from one Android-first field shell.",
    monitor:
      "Keep live runtime and session state visible while field execution remains the primary release path.",
    species:
      "Keep jurisdiction-aware species reference lookups nearby without leaving the survey shell.",
    settings:
      "Check runtime health, offline readiness, and sync state without leaving the field release workspace.",
    analyze:
      "Turn audio into species-level evidence packages with charts and reports.",
    verify: "Confirm, reject, and annotate detections before interpretation.",
    devices:
      "Register low-power field units and keep location provenance aligned.",
    embeddings: "Inspect acoustic structure, similarity, and novelty events.",
    sdm: "Translate site evidence into spatial planning views.",
    search: "Use external reference recordings for comparison and lookup.",
    about:
      "Keep the platform tied to the biodiversity survey release narrative.",
    phenology:
      "Seasonal vocal activity patterns, onset trends, and phenological shifts.",
    occupancy:
      "Estimate true occupancy corrected for imperfect detection probability.",
    fewshot:
      "Create custom detectors for rare species from just 1-5 reference recordings.",
    soundscape:
      "Ecoacoustic indices, ecosystem health scoring, and degradation signals.",
  },
  zh: {
    dashboard: "一览野外调查进度、最近观测记录和系统状态。",
    fieldops:
      "在一个 Android 优先的野外壳层中完成脊椎动物、植物和昆虫的离线调查。",
    monitor: "在野外执行保持主线的同时，查看运行状态与会话信息。",
    species: "在不离开调查壳层的前提下进行分辖区物种参考查询。",
    settings: "在不离开发布主线的情况下查看运行健康、离线准备和同步状态。",
    analyze: "把音频转换为可复核的物种级证据包。",
    verify: "在解释前确认、否决和标注检测结果。",
    devices: "注册低功耗野外设备，保持位置和来源可追踪。",
    embeddings: "探索声学结构、相似性与新奇事件。",
    sdm: "把监测证据连接到空间部署与保护规划。",
    search: "检索外部参考录音进行对照。",
    about: "保持平台与生物多样性调查发布定位一致。",
    phenology: "季节性发声活动规律、起始趋势和物候漂移分析。",
    occupancy: "校正不完美检测概率后的真实占域概率估计。",
    fewshot: "仅需 1-5 条参考录音即可为稀有种创建自定义检测器。",
    soundscape: "声景指数、生态系统健康评分和退化信号监测。",
  },
};

export const COLORS = [
  "#34d399",
  "#06b6d4",
  "#a78bfa",
  "#fbbf24",
  "#f87171",
  "#f472b6",
  "#2dd4bf",
  "#fb923c",
  "#818cf8",
  "#a3e635",
];
