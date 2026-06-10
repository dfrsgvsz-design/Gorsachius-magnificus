/**
 * Protocol engine: constants, protocol catalog definitions, i18n copy,
 * and all pure functions for protocol selection, field building,
 * taxonomy matching, and validation.
 *
 * Extracted from FieldOpsTab.jsx lines 111-875.
 */
import { toArray, EXPORT_JURISDICTIONS } from './fieldOpsUtils'

// ──────────────────────────────────────────────
// Small constants
// ──────────────────────────────────────────────

export const TAXA = ['birds', 'mammals', 'amphibians', 'reptiles', 'plants', 'insects', 'traces']
export const DEFAULT_REMOTE_TILE_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
export const DEFAULT_FIELD_TILE_PROXY_URL = '/api/maps/tiles/{z}/{x}/{y}'

export const PROGRAM_OPTIONS = [
  {
    id: 'terrestrial_vertebrates',
    label: 'Terrestrial vertebrates',
    label_zh: '陆生脊椎动物',
    description: 'Bird surveys, point counts, mammal trapping, and herp camera work share one field shell.',
    description_zh: '鸟类样线、样点计数、兽类陷阱和两爬红外相机共用同一个野外工作界面。',
  },
  {
    id: 'plants',
    label: 'Plants',
    label_zh: '植物',
    description: 'Quadrat and transect vegetation recording stays isolated from vertebrate workflows.',
    description_zh: '样方和样线植被记录独立于脊椎动物工作流。',
  },
  {
    id: 'insects',
    label: 'Insects',
    label_zh: '昆虫',
    description: 'Insect transects keep their own effort and record fields while syncing to the same backend.',
    description_zh: '昆虫样线保留独立的调查努力量和记录字段，同步到同一后端。',
  },
]

export const TERRESTRIAL_VERTEBRATE_PROTOCOLS = new Set([
  'bird_line_transect',
  'bird_point_count',
  'mammal_trap_net',
  'herp_infrared_camera',
])

export const VERTEBRATE_SUBMODULES = [
  {
    id: 'birds',
    label: 'Birds',
    label_zh: '鸟类',
    taxonGroup: 'birds',
    protocolIds: ['bird_line_transect', 'bird_point_count'],
  },
  {
    id: 'mammals',
    label: 'Mammals',
    label_zh: '兽类',
    taxonGroup: 'mammals',
    protocolIds: ['mammal_trap_net'],
  },
  {
    id: 'amphibians',
    label: 'Amphibians',
    label_zh: '两栖类',
    taxonGroup: 'amphibians',
    protocolIds: ['herp_infrared_camera'],
  },
  {
    id: 'reptiles',
    label: 'Reptiles',
    label_zh: '爬行类',
    taxonGroup: 'reptiles',
    protocolIds: ['herp_infrared_camera'],
  },
]

// ──────────────────────────────────────────────
// Protocol definitions (full catalog)
// ──────────────────────────────────────────────

export const PROTOCOL_OPTIONS = [
  {
    id: 'bird_line_transect',
    program: 'terrestrial_vertebrates',
    label: 'Bird line transect',
    label_zh: '鸟类样线法',
    shellLabel: 'Transect walk',
    shellLabel_zh: '样线行走',
    description: 'Walk one route and record birds with route-linked detections and effort.',
    description_zh: '沿样线行走，记录鸟类及其距离带、发现方式和调查努力量。',
    assetLabel: 'Transect route',
    assetLabel_zh: '样线路线',
    assetHint: 'Select or import the transect line used for the bird walk.',
    assetHint_zh: '选择或导入本次鸟类调查使用的样线。',
    requiresAsset: true,
    supportsTrack: true,
    defaultTaxonGroup: 'birds',
    defaultEvidenceType: 'visual',
    vertebrateSubmodules: ['birds'],
    allowedTaxonGroups: ['birds'],
    eventFields: [
      { key: 'transect_name', label: 'Transect name', placeholder: 'North ridge transect', required: true },
      { key: 'transect_length_m', label: 'Transect length (m)', type: 'number', placeholder: '1200', required: true },
      { key: 'survey_round', label: 'Survey round', placeholder: 'Round 1', required: true },
      { key: 'observer_count', label: 'Observer count', type: 'number', placeholder: '2', required: true },
      { key: 'distance_walked_m', label: 'Distance walked (m)', type: 'number', placeholder: '1150', required: true },
      { key: 'duration_min', label: 'Duration (min)', type: 'number', placeholder: '65', required: true },
      { key: 'pace_m_per_min', label: 'Pace (m/min)', type: 'number', placeholder: '18' },
      { key: 'wind_code', label: 'Wind code', placeholder: '0-5', options: [
        { value: '0', label: '0 - Calm', label_zh: '0 - 静风' },
        { value: '1', label: '1 - Light air', label_zh: '1 - 软风' },
        { value: '2', label: '2 - Light breeze', label_zh: '2 - 轻风' },
        { value: '3', label: '3 - Gentle breeze', label_zh: '3 - 微风' },
        { value: '4', label: '4 - Moderate breeze', label_zh: '4 - 和风' },
        { value: '5', label: '5 - Fresh breeze', label_zh: '5 - 清风' },
      ] },
      { key: 'cloud_code', label: 'Cloud code', placeholder: '0-10', options: [
        { value: '0', label: '0/10' }, { value: '1', label: '1/10' }, { value: '2', label: '2/10' },
        { value: '3', label: '3/10' }, { value: '4', label: '4/10' }, { value: '5', label: '5/10' },
        { value: '6', label: '6/10' }, { value: '7', label: '7/10' }, { value: '8', label: '8/10' },
        { value: '9', label: '9/10' }, { value: '10', label: '10/10' },
      ] },
      { key: 'precipitation_code', label: 'Precipitation code', placeholder: 'none / light / rain', options: [
        { value: 'none', label: 'None', label_zh: '无' },
        { value: 'drizzle', label: 'Drizzle', label_zh: '毛毛雨' },
        { value: 'light', label: 'Light rain', label_zh: '小雨' },
        { value: 'rain', label: 'Rain', label_zh: '中雨' },
        { value: 'heavy', label: 'Heavy rain', label_zh: '大雨' },
      ] },
      { key: 'habitat_type', label: 'Habitat type', placeholder: 'Evergreen broadleaf forest', options: [
        { value: 'evergreen_broadleaf', label: 'Evergreen broadleaf forest', label_zh: '常绿阔叶林' },
        { value: 'deciduous_broadleaf', label: 'Deciduous broadleaf forest', label_zh: '落叶阔叶林' },
        { value: 'mixed_forest', label: 'Mixed forest', label_zh: '针阔混交林' },
        { value: 'coniferous', label: 'Coniferous forest', label_zh: '针叶林' },
        { value: 'bamboo', label: 'Bamboo forest', label_zh: '竹林' },
        { value: 'shrubland', label: 'Shrubland', label_zh: '灌丛' },
        { value: 'grassland', label: 'Grassland', label_zh: '草地' },
        { value: 'wetland', label: 'Wetland', label_zh: '湿地' },
        { value: 'farmland', label: 'Farmland', label_zh: '农田' },
        { value: 'urban', label: 'Urban / village', label_zh: '城镇/村落' },
        { value: 'river_stream', label: 'River / stream', label_zh: '河流/溪流' },
        { value: 'forest_edge', label: 'Forest edge', label_zh: '林缘' },
      ] },
      { key: 'disturbance_notes', label: 'Disturbance notes', placeholder: 'Trail traffic near lower section' },
    ],
    recordFields: [
      { key: 'detection_type', label: 'Detection type', placeholder: 'seen / heard / mixed', required: true, options: [
        { value: 'seen', label: 'Seen', label_zh: '目击' },
        { value: 'heard', label: 'Heard', label_zh: '鸣声' },
        { value: 'mixed', label: 'Mixed (seen + heard)', label_zh: '混合（目击+鸣声）' },
      ] },
      { key: 'distance_band', label: 'Distance band', placeholder: '0-25m', required: true, options: [
        { value: '0-10m', label: '0–10 m' },
        { value: '10-25m', label: '10–25 m' },
        { value: '25-50m', label: '25–50 m' },
        { value: '50-100m', label: '50–100 m' },
        { value: '100-200m', label: '100–200 m' },
        { value: '>200m', label: '> 200 m' },
      ] },
      { key: 'bearing', label: 'Bearing', placeholder: 'NE / 35°', options: [
        { value: 'N', label: 'N', label_zh: '北' },
        { value: 'NE', label: 'NE', label_zh: '东北' },
        { value: 'E', label: 'E', label_zh: '东' },
        { value: 'SE', label: 'SE', label_zh: '东南' },
        { value: 'S', label: 'S', label_zh: '南' },
        { value: 'SW', label: 'SW', label_zh: '西南' },
        { value: 'W', label: 'W', label_zh: '西' },
        { value: 'NW', label: 'NW', label_zh: '西北' },
      ] },
      { key: 'breeding_code', label: 'Breeding code', placeholder: 'A / B / C', options: [
        { value: 'A', label: 'A – Possible breeding', label_zh: 'A – 可能繁殖' },
        { value: 'B', label: 'B – Probable breeding', label_zh: 'B – 很可能繁殖' },
        { value: 'C', label: 'C – Confirmed breeding', label_zh: 'C – 确认繁殖' },
      ] },
      { key: 'flock_size', label: 'Flock size', type: 'number', placeholder: '6' },
      { key: 'route_segment_id', label: 'Route segment ID', placeholder: 'seg-02' },
    ],
  },
  {
    id: 'bird_point_count',
    program: 'terrestrial_vertebrates',
    label: 'Bird point count',
    label_zh: '鸟类样点法',
    shellLabel: 'Point count station',
    shellLabel_zh: '样点计数',
    description: 'Use one fixed station or short segment and capture count duration and radius.',
    description_zh: '在固定样点定时计数，记录观测时长和半径。',
    assetLabel: 'Point count asset',
    assetLabel_zh: '样点资料',
    assetHint: 'Select a station route or segment if one is available for this point count.',
    assetHint_zh: '如果已有预设样点，请选择对应的站点或路段。',
    requiresAsset: false,
    supportsTrack: false,
    defaultTaxonGroup: 'birds',
    defaultEvidenceType: 'audio',
    vertebrateSubmodules: ['birds'],
    allowedTaxonGroups: ['birds'],
    eventFields: [
      { key: 'point_id', label: 'Point ID', placeholder: 'PC-01', required: true },
      { key: 'point_visit_index', label: 'Visit index', type: 'number', placeholder: '1', required: true },
      { key: 'point_duration_min', label: 'Point duration (min)', type: 'number', placeholder: '10', required: true },
      { key: 'observer_count', label: 'Observer count', type: 'number', placeholder: '1', required: true },
      { key: 'point_radius_m', label: 'Point radius (m)', type: 'number', placeholder: '100' },
      { key: 'station_count', label: 'Station count', type: 'number', placeholder: '1' },
      { key: 'travel_distance_m', label: 'Travel distance (m)', type: 'number', placeholder: '0' },
      { key: 'wind_code', label: 'Wind code', placeholder: '0-5' },
      { key: 'cloud_code', label: 'Cloud code', placeholder: '0-10' },
      { key: 'precipitation_code', label: 'Precipitation code', placeholder: 'none / drizzle' },
      { key: 'habitat_type', label: 'Habitat type', placeholder: 'Forest edge' },
    ],
    recordFields: [
      { key: 'detection_type', label: 'Detection type', placeholder: 'heard / seen', required: true, options: [
        { value: 'seen', label: 'Seen', label_zh: '目击' },
        { value: 'heard', label: 'Heard', label_zh: '鸣声' },
        { value: 'mixed', label: 'Mixed', label_zh: '混合' },
      ] },
      { key: 'distance_band', label: 'Distance band', placeholder: '0-50m', required: true, options: [
        { value: '0-25m', label: '0–25 m' },
        { value: '25-50m', label: '25–50 m' },
        { value: '50-100m', label: '50–100 m' },
        { value: '>100m', label: '> 100 m' },
      ] },
      { key: 'breeding_code', label: 'Breeding code', placeholder: 'A / B / C', options: [
        { value: 'A', label: 'A – Possible', label_zh: 'A – 可能繁殖' },
        { value: 'B', label: 'B – Probable', label_zh: 'B – 很可能繁殖' },
        { value: 'C', label: 'C – Confirmed', label_zh: 'C – 确认繁殖' },
      ] },
      { key: 'point_id', label: 'Point ID override', placeholder: 'PC-01' },
      { key: 'flock_size', label: 'Flock size', type: 'number', placeholder: '3' },
    ],
  },
  {
    id: 'mammal_trap_net',
    program: 'terrestrial_vertebrates',
    label: 'Mammal trap / net',
    label_zh: '兽类陷阱/网捕',
    shellLabel: 'Trap or net event',
    shellLabel_zh: '陷阱/网捕事件',
    description: 'Track trap lines, net checks, and specimen or release records for mammals.',
    description_zh: '记录陷阱布设、检查、捕获和释放信息。',
    assetLabel: 'Trap or net asset',
    assetLabel_zh: '陷阱/网具资料',
    assetHint: 'Select a trap line or station route if you want the captures tied to one asset.',
    assetHint_zh: '如需将捕获记录关联到特定路线，请选择陷阱线或站点。',
    requiresAsset: false,
    supportsTrack: false,
    defaultTaxonGroup: 'mammals',
    defaultEvidenceType: 'trace',
    vertebrateSubmodules: ['mammals'],
    allowedTaxonGroups: ['mammals'],
    eventFields: [
      { key: 'trap_method', label: 'Trap / net method', placeholder: 'Sherman trap / mist net', required: true },
      { key: 'trap_station_count', label: 'Trap station count', type: 'number', placeholder: '12', required: true },
      { key: 'deployment_start_time', label: 'Deployment start time', placeholder: '2026-04-19T18:00:00Z', required: true },
      { key: 'deployment_end_time', label: 'Deployment end time', placeholder: '2026-04-20T06:00:00Z', required: true },
      { key: 'bait_type', label: 'Bait type', placeholder: 'peanut + oats', required: true },
      { key: 'observer_count', label: 'Observer count', type: 'number', placeholder: '2', required: true },
      { key: 'trap_model', label: 'Trap model', placeholder: 'Sherman folding' },
      { key: 'check_interval_h', label: 'Check interval (h)', type: 'number', placeholder: '12' },
      { key: 'microhabitat', label: 'Microhabitat', placeholder: 'Bamboo understory' },
      { key: 'permit_reference', label: 'Permit reference', placeholder: 'Permit-2026-01' },
      { key: 'welfare_notes', label: 'Welfare notes', placeholder: 'Shade checked, water provided' },
      { key: 'trap_nights', label: 'Trap nights', type: 'number', placeholder: '24' },
      { key: 'active_trap_count', label: 'Active trap count', type: 'number', placeholder: '12' },
      { key: 'checked_station_count', label: 'Checked station count', type: 'number', placeholder: '12' },
    ],
    recordFields: [
      { key: 'capture_status', label: 'Capture status', placeholder: 'captured / empty / disturbed', required: true, options: [
        { value: 'captured', label: 'Captured', label_zh: '捕获' },
        { value: 'empty', label: 'Empty', label_zh: '空' },
        { value: 'disturbed', label: 'Disturbed', label_zh: '被干扰' },
      ] },
      { key: 'trap_station_id', label: 'Trap station ID', placeholder: 'MAM-05', required: true },
      { key: 'mark_code', label: 'Mark code', placeholder: 'ear-tag-12' },
      { key: 'sex', label: 'Sex', placeholder: 'male / female / unknown', options: [
        { value: 'male', label: 'Male', label_zh: '雄' },
        { value: 'female', label: 'Female', label_zh: '雌' },
        { value: 'unknown', label: 'Unknown', label_zh: '未知' },
      ] },
      { key: 'life_stage', label: 'Life stage', placeholder: 'adult / juvenile', options: [
        { value: 'adult', label: 'Adult', label_zh: '成体' },
        { value: 'juvenile', label: 'Juvenile', label_zh: '幼体' },
        { value: 'subadult', label: 'Subadult', label_zh: '亚成体' },
      ] },
      { key: 'body_mass_g', label: 'Body mass (g)', type: 'number', placeholder: '120' },
      { key: 'release_status', label: 'Release status', placeholder: 'released / retained / escaped', options: [
        { value: 'released', label: 'Released', label_zh: '释放' },
        { value: 'retained', label: 'Retained', label_zh: '保留' },
        { value: 'escaped', label: 'Escaped', label_zh: '逃脱' },
      ] },
      { key: 'sample_collected', label: 'Sample collected', placeholder: 'hair / feces / blood / none', options: [
        { value: 'none', label: 'None', label_zh: '无' },
        { value: 'hair', label: 'Hair', label_zh: '毛发' },
        { value: 'feces', label: 'Feces', label_zh: '粪便' },
        { value: 'blood', label: 'Blood', label_zh: '血液' },
      ] },
    ],
  },
  {
    id: 'herp_infrared_camera',
    program: 'terrestrial_vertebrates',
    label: 'Herp infrared camera',
    label_zh: '两爬红外相机',
    shellLabel: 'Infrared camera station',
    shellLabel_zh: '红外相机站点',
    description: 'Deploy, check, and retrieve infrared cameras for amphibians and reptiles.',
    description_zh: '部署、检查和回收用于两栖爬行动物监测的红外相机。',
    assetLabel: 'Camera station',
    assetLabel_zh: '相机站点',
    assetHint: 'Select a camera station or route if one has already been planned for this site.',
    assetHint_zh: '如已有预设相机站点，请选择对应的站点或路线。',
    requiresAsset: false,
    supportsTrack: false,
    defaultTaxonGroup: 'amphibians',
    defaultEvidenceType: 'visual',
    vertebrateSubmodules: ['amphibians', 'reptiles'],
    allowedTaxonGroups: ['amphibians', 'reptiles'],
    eventFields: [
      { key: 'camera_station_id', label: 'Camera station ID', placeholder: 'HERP-CAM-02', required: true },
      { key: 'camera_action', label: 'Camera action', placeholder: 'deploy / check / retrieve', required: true, options: [
        { value: 'deploy', label: 'Deploy', label_zh: '布设' },
        { value: 'check', label: 'Check', label_zh: '检查' },
        { value: 'retrieve', label: 'Retrieve', label_zh: '回收' },
      ] },
      { key: 'deployment_start_time', label: 'Deployment start time', placeholder: '2026-04-19T18:00:00Z', required: true },
      { key: 'deployment_end_time', label: 'Deployment end time', placeholder: '2026-04-29T18:00:00Z', required: true },
      { key: 'camera_model', label: 'Camera model', placeholder: 'HC550M', required: true },
      { key: 'observer_count', label: 'Observer count', type: 'number', placeholder: '2', required: true },
      { key: 'sensor_mode', label: 'Sensor mode', placeholder: 'IR motion / time lapse', options: [
        { value: 'ir_motion', label: 'IR motion', label_zh: '红外感应' },
        { value: 'time_lapse', label: 'Time lapse', label_zh: '延时拍摄' },
        { value: 'hybrid', label: 'Hybrid', label_zh: '混合模式' },
      ] },
      { key: 'trigger_interval_s', label: 'Trigger interval (s)', type: 'number', placeholder: '30' },
      { key: 'camera_height_cm', label: 'Camera height (cm)', type: 'number', placeholder: '25' },
      { key: 'orientation', label: 'Orientation', placeholder: 'SE / 135°' },
      { key: 'bait_lure', label: 'Bait / lure', placeholder: 'none / fish oil' },
      { key: 'habitat', label: 'Habitat', placeholder: 'stream bank' },
      { key: 'camera_days', label: 'Camera days', type: 'number', placeholder: '10' },
      { key: 'active_camera_count', label: 'Active camera count', type: 'number', placeholder: '4' },
      { key: 'file_count', label: 'File count', type: 'number', placeholder: '240' },
    ],
    recordFields: [
      { key: 'camera_station_id', label: 'Camera station ID', placeholder: 'HERP-CAM-02', required: true },
      { key: 'individual_count', label: 'Individual count', type: 'number', placeholder: '1' },
      { key: 'life_stage', label: 'Life stage', placeholder: 'adult / juvenile / larva', options: [
        { value: 'adult', label: 'Adult', label_zh: '成体' },
        { value: 'juvenile', label: 'Juvenile', label_zh: '幼体' },
        { value: 'larva', label: 'Larva', label_zh: '幼虫/蝌蚪' },
      ] },
      { key: 'media_file_id', label: 'Media file ID', placeholder: 'IMG_0001' },
      { key: 'sequence_id', label: 'Sequence ID', placeholder: 'SEQ-12' },
    ],
  },
  {
    id: 'plant_quadrat',
    program: 'plants',
    label: 'Plant quadrat',
    label_zh: '植物样方法',
    shellLabel: 'Quadrat event',
    shellLabel_zh: '样方调查',
    description: 'Record one vegetation quadrat with area, layer, cover, and species attributes.',
    description_zh: '记录样方内植被种类、盖度、高度和物候。',
    assetLabel: 'Quadrat asset',
    assetLabel_zh: '样方资料',
    assetHint: 'Select a plot or small route segment if you have one prepared for this quadrat.',
    assetHint_zh: '如已有预设样方，请选择对应的样地或路段。',
    requiresAsset: false,
    supportsTrack: false,
    defaultTaxonGroup: 'plants',
    defaultEvidenceType: 'visual',
    eventFields: [
      { key: 'quadrat_code', label: 'Quadrat code', placeholder: 'Q-01' },
      { key: 'quadrat_area_m2', label: 'Quadrat area (m2)', type: 'number', placeholder: '1' },
      { key: 'vegetation_layer', label: 'Vegetation layer', placeholder: 'Tree / shrub / herb', options: [
        { value: 'tree', label: 'Tree layer', label_zh: '乔木层' },
        { value: 'shrub', label: 'Shrub layer', label_zh: '灌木层' },
        { value: 'herb', label: 'Herb layer', label_zh: '草本层' },
        { value: 'ground', label: 'Ground layer', label_zh: '地被层' },
      ] },
    ],
    recordFields: [
      { key: 'cover_percent', label: 'Cover (%)', type: 'number', placeholder: '30' },
      { key: 'height_cm', label: 'Height (cm)', type: 'number', placeholder: '45' },
      { key: 'phenology', label: 'Phenology', placeholder: 'Flowering / fruiting / vegetative', options: [
        { value: 'flowering', label: 'Flowering', label_zh: '花期' },
        { value: 'fruiting', label: 'Fruiting', label_zh: '果期' },
        { value: 'vegetative', label: 'Vegetative', label_zh: '营养期' },
        { value: 'dormant', label: 'Dormant', label_zh: '休眠期' },
      ] },
    ],
  },
  {
    id: 'plant_transect',
    program: 'plants',
    label: 'Plant transect',
    label_zh: '植物样线法',
    shellLabel: 'Vegetation transect',
    shellLabel_zh: '植被样线',
    description: 'Use route-linked segments for vegetation transects and layer-based records.',
    description_zh: '沿样线记录植被种类和分布，按植被层记录。',
    assetLabel: 'Plant transect',
    assetLabel_zh: '植物样线',
    assetHint: 'Select or import the vegetation transect used for this sampling event.',
    assetHint_zh: '选择或导入本次植被调查使用的样线。',
    requiresAsset: true,
    supportsTrack: true,
    defaultTaxonGroup: 'plants',
    defaultEvidenceType: 'visual',
    eventFields: [
      { key: 'segment_length_m', label: 'Segment length (m)', type: 'number', placeholder: '100' },
      { key: 'transect_width_m', label: 'Transect width (m)', type: 'number', placeholder: '5' },
      { key: 'vegetation_layer', label: 'Vegetation layer', placeholder: 'Tree / shrub / herb', options: [
        { value: 'tree', label: 'Tree layer', label_zh: '乔木层' },
        { value: 'shrub', label: 'Shrub layer', label_zh: '灌木层' },
        { value: 'herb', label: 'Herb layer', label_zh: '草本层' },
        { value: 'ground', label: 'Ground layer', label_zh: '地被层' },
      ] },
    ],
    recordFields: [
      { key: 'cover_percent', label: 'Cover (%)', type: 'number', placeholder: '40' },
      { key: 'height_cm', label: 'Height (cm)', type: 'number', placeholder: '120' },
      { key: 'growth_form', label: 'Growth form', placeholder: 'Tree / shrub / vine / herb', options: [
        { value: 'tree', label: 'Tree', label_zh: '乔木' },
        { value: 'shrub', label: 'Shrub', label_zh: '灌木' },
        { value: 'vine', label: 'Vine', label_zh: '藤本' },
        { value: 'herb', label: 'Herb', label_zh: '草本' },
        { value: 'fern', label: 'Fern', label_zh: '蕨类' },
      ] },
    ],
  },
  {
    id: 'insect_transect',
    program: 'insects',
    label: 'Insect transect',
    label_zh: '昆虫样线法',
    shellLabel: 'Insect transect',
    shellLabel_zh: '昆虫样线',
    description: 'Walk a transect and capture insect counts with weather and detection context.',
    description_zh: '沿样线行走，记录昆虫种类和数量，并记录天气和发现情境。',
    assetLabel: 'Insect transect',
    assetLabel_zh: '昆虫样线',
    assetHint: 'Select or import the transect segment used for the insect survey.',
    assetHint_zh: '选择或导入本次昆虫调查使用的样线。',
    requiresAsset: true,
    supportsTrack: true,
    defaultTaxonGroup: 'insects',
    defaultEvidenceType: 'visual',
    eventFields: [
      { key: 'transect_width_m', label: 'Transect width (m)', type: 'number', placeholder: '5' },
      { key: 'weather_window', label: 'Weather window', placeholder: 'Sunny, low wind' },
      { key: 'pace_note', label: 'Walk pace', placeholder: 'Constant pace / sweep count' },
    ],
    recordFields: [
      { key: 'life_stage', label: 'Life stage', placeholder: 'Adult / larva / pupa', options: [
        { value: 'adult', label: 'Adult', label_zh: '成虫' },
        { value: 'larva', label: 'Larva', label_zh: '幼虫' },
        { value: 'pupa', label: 'Pupa', label_zh: '蛹' },
      ] },
      { key: 'distance_band_m', label: 'Distance band (m)', type: 'number', placeholder: '2' },
      { key: 'behavior_code', label: 'Behavior code', placeholder: 'Flying / basking / feeding', options: [
        { value: 'flying', label: 'Flying', label_zh: '飞行' },
        { value: 'basking', label: 'Basking', label_zh: '晒太阳' },
        { value: 'feeding', label: 'Feeding', label_zh: '取食' },
        { value: 'resting', label: 'Resting', label_zh: '静息' },
      ] },
    ],
  },
]

// ──────────────────────────────────────────────
// i18n copy
// ──────────────────────────────────────────────

export const COPY = {
  en: {
    badge: 'Offline Biodiversity Survey',
    title: 'Biodiversity field survey workspace',
    body: 'Prepare routes or stations, cache offline maps, capture observations and attachments, restore sessions after interruptions, and sync safely when a connection returns.',
    pilotTitle: 'Release workflow',
    pilotBody: 'Complete route, station, or quadrat work offline on Android, then restore, sync, and export without developer intervention.',
    offline: 'Offline',
    online: 'Online',
    pull: 'Pull',
    push: 'Push',
    project: 'Project',
    projectPlaceholder: 'Project name',
    regionPlaceholder: 'Region or reserve',
    createProject: 'Create project',
    site: 'Site',
    sitePlaceholder: 'Site name',
    habitatPlaceholder: 'Habitat type',
    saveSite: 'Save site',
    map: 'Offline map',
    transect: 'Route or station asset',
    selectTransect: 'Select asset',
    selectTransectHint: 'Select a route, station, or plot asset when the current protocol needs one.',
    preloadMap: 'Preload tiles',
    importRoute: 'Import route',
    exportGeoJSON: 'GeoJSON',
    exportGpx: 'GPX',
    observation: 'Quick observation',
    speciesPlaceholder: 'Chinese, English, or scientific name',
    evidenceVisual: 'Visual',
    evidenceAudio: 'Audio',
    evidenceTrace: 'Trace',
    saveObservation: 'Save observation',
    track: 'Track recorder',
    startTrack: 'Start track',
    stopTrack: 'Stop track',
    media: 'Media inbox',
    sync: 'Sync center',
    attachments: 'Attachments',
    capturePhoto: 'Take photo',
    captureAudioStart: 'Record audio',
    captureAudioStop: 'Stop audio',
    confidence: 'Confidence',
    count: 'Count',
    observer: 'Observer',
    weather: 'Weather',
    behavior: 'Behavior / notes',
    location: 'Use current GPS',
    noProject: 'A default field project will be created automatically if none exists.',
    routeSummary: 'Planned vs recorded',
    routeLength: 'Route length',
    recordsOnTransect: 'Observations',
    speciesLabel: 'species',
    effort: 'Effort',
    transectNotes: 'Event notes',
    walkStart: 'Event start',
    walks: 'walks',
    transectReport: 'Route or station report',
    loadingReport: 'Loading route or station summary...',
    reportOfflineHint: 'Reconnect to load the latest route or station summary and enable report exports.',
    emptyReportSummary: 'The server did not return a route or station summary for this selection yet.',
    noSpeciesRows: 'No species rows in this report yet.',
    noObservers: 'No observers listed',
    noWeather: 'No weather summary',
    speciesList: 'Species list',
    serverSummary: 'server summary',
    routeReady: 'Selected asset',
    routeMissing: 'Asset needed',
    walkActive: 'Walk active',
    walkIdle: 'Walk idle',
    syncBacklog: 'Sync backlog',
    routeSelectionStep: '1. Select or import the route, station, or plot asset for the active site.',
    walkRecordingStep: '2. Start a walk when the protocol is route-based so GPS effort and timing stay attached to that asset.',
    speciesRecordingStep: '3. Save observations with evidence, observer, taxonomy, and protocol-specific context.',
    syncReportStep: '4. Sync queued work and export the protocol bundle when online.',
    unknownTaxon: 'Unknown taxon',
    traceOnly: 'Trace only',
    queueEmpty: 'Nothing waiting in the sync queue.',
    conflicts: 'Conflicts',
    mapNote: 'Tile downloads use browser cache so the same area can reopen without network.',
  },
  zh: {
    badge: '离线外业调查',
    title: '中国野生动物外业调查工作区',
    body: '在同一个界面里完成调查项目管理、路线导入、离线底图缓存、轨迹记录、观察录入、媒体证据保存和联网后的安全同步。',
    pilotTitle: '发布工作流',
    pilotBody: '在 Android 上离线完成路线、样点或样方工作，然后恢复、同步并导出，无需开发人员介入。',
    offline: '离线',
    online: '在线',
    pull: '拉取',
    push: '推送',
    project: '项目',
    projectPlaceholder: '项目名称',
    regionPlaceholder: '保护地或区域',
    createProject: '新建项目',
    site: '样点',
    sitePlaceholder: '样点名称',
    habitatPlaceholder: '生境类型',
    saveSite: '保存样点',
    map: '离线地图',
    transect: '路线或站点资料',
    selectTransect: '选择资料',
    selectTransectHint: '当前协议需要路线、站点或样地资料时，请在此选择。',
    preloadMap: '缓存底图',
    importRoute: '导入路线',
    exportGeoJSON: '导出 GeoJSON',
    exportGpx: '导出 GPX',
    observation: '快速观察记录',
    speciesPlaceholder: '中文名、英文名或学名',
    evidenceVisual: '目击',
    evidenceAudio: '声音',
    evidenceTrace: '痕迹',
    saveObservation: '保存记录',
    track: '轨迹记录',
    startTrack: '开始记录',
    stopTrack: '结束记录',
    media: '媒体收件箱',
    sync: '同步中心',
    attachments: '附件',
    capturePhoto: '拍照',
    captureAudioStart: '录音',
    captureAudioStop: '停止录音',
    confidence: '可信度',
    count: '数量',
    observer: '观察者',
    weather: '天气',
    behavior: '行为 / 备注',
    location: '使用当前 GPS',
    noProject: '如果本地还没有项目，会自动创建一个默认项目。',
    routeSummary: '计划路线与实走轨迹',
    routeLength: '路线长度',
    recordsOnTransect: '观测记录',
    speciesLabel: '物种',
    effort: '调查努力量',
    transectNotes: '事件备注',
    walkStart: '事件开始',
    walks: '次行走',
    transectReport: '路线或站点报告',
    loadingReport: '正在加载路线或站点汇总...',
    reportOfflineHint: '请连接网络以加载最新汇总并启用报告导出。',
    emptyReportSummary: '服务器尚未返回该选择的路线或站点汇总。',
    noSpeciesRows: '本报告暂无物种记录。',
    noObservers: '未列出观察者',
    noWeather: '无天气摘要',
    speciesList: '物种名录',
    serverSummary: '服务器汇总',
    routeReady: '已选资料',
    routeMissing: '需要资料',
    walkActive: '行走中',
    walkIdle: '空闲',
    syncBacklog: '同步积压',
    unknownTaxon: '未知类群',
    traceOnly: '仅痕迹',
    queueEmpty: '当前没有待同步操作。',
    conflicts: '冲突',
    mapNote: '底图缓存使用浏览器 Cache API，同一区域在离线时也能再次打开。',
    routeSelectionStep: '1. 为当前样点选择或导入路线、站点或样地资料。',
    walkRecordingStep: '2. 协议为路线型时开始行走，GPS 自动记录轨迹和时间。',
    speciesRecordingStep: '3. 保存观测记录，包含证据类型、观察者、分类和协议字段。',
    syncReportStep: '4. 联网后同步并导出协议数据包。',
  },
}

// ──────────────────────────────────────────────
// Pure utility functions
// ──────────────────────────────────────────────

export function pickLocale(i18n) {
  return i18n.resolvedLanguage?.startsWith('zh') ? 'zh' : 'en'
}

// ──────────────────────────────────────────────
// Field label Chinese translations
// ──────────────────────────────────────────────

const FIELD_LABELS_ZH = {
  observer_count: '观察者人数', habitat_type: '生境类型', wind_code: '风力等级',
  cloud_code: '云量等级', precipitation_code: '降水情况', habitat: '生境',
  transect_name: '样线名称', transect_length_m: '样线长度（米）', survey_round: '调查轮次',
  distance_walked_m: '行走距离（米）', duration_min: '时长（分钟）', pace_m_per_min: '步速（米/分钟）',
  disturbance_notes: '干扰记录', detection_type: '发现方式', distance_band: '距离带',
  bearing: '方位角', breeding_code: '繁殖行为代码', flock_size: '群体大小',
  route_segment_id: '路段编号', point_id: '样点编号', point_visit_index: '访问序号',
  point_duration_min: '观测时长（分钟）', point_radius_m: '样点半径（米）',
  station_count: '站点数量', travel_distance_m: '移动距离（米）',
  trap_method: '陷阱/网捕方法', trap_station_count: '陷阱站点数',
  deployment_start_time: '布设开始时间', deployment_end_time: '布设结束时间',
  bait_type: '诱饵类型', trap_model: '陷阱型号', check_interval_h: '检查间隔（小时）',
  microhabitat: '微生境', permit_reference: '许可证编号', welfare_notes: '动物福利记录',
  trap_nights: '陷阱夜数', active_trap_count: '有效陷阱数',
  checked_station_count: '已检查站点数', capture_status: '捕获状态',
  trap_station_id: '陷阱站点编号', mark_code: '标记编号', sex: '性别',
  life_stage: '生活史阶段', body_mass_g: '体重（克）', release_status: '释放状态',
  sample_collected: '采集样品', camera_station_id: '相机站点编号', camera_action: '操作类型',
  camera_model: '相机型号', sensor_mode: '传感器模式', trigger_interval_s: '触发间隔（秒）',
  camera_height_cm: '安装高度（厘米）', orientation: '朝向', bait_lure: '诱饵/引诱物',
  camera_days: '相机天数', active_camera_count: '有效相机数', file_count: '文件数量',
  individual_count: '个体数量', media_file_id: '媒体文件编号', sequence_id: '序列编号',
  quadrat_code: '样方编号', quadrat_area_m2: '样方面积（m²）', vegetation_layer: '植被层',
  cover_percent: '盖度（%）', height_cm: '高度（厘米）', phenology: '物候期',
  segment_length_m: '段长（米）', transect_width_m: '样带宽度（米）', growth_form: '生长型',
  weather_window: '天气窗口', pace_note: '行走速度', distance_band_m: '距离带（米）',
  behavior_code: '行为代码',
}

const FIELD_PLACEHOLDERS_ZH = {
  transect_name: '北岭样线', survey_round: '第1轮', habitat_type: '常绿阔叶林',
  disturbance_notes: '步道附近有行人干扰', detection_type: '目击 / 鸣声 / 混合',
  distance_band: '0-25m', bearing: '东北 / 35°', breeding_code: 'A / B / C',
  route_segment_id: 'seg-02', point_id: 'PC-01', habitat: '溪岸',
  trap_method: '铗夹 / 雾网', bait_type: '花生+燕麦', trap_model: 'Sherman折叠式',
  microhabitat: '竹林林下', permit_reference: '许可证-2026-01',
  welfare_notes: '已检查遮阴，提供饮水', capture_status: '捕获 / 空 / 被干扰',
  trap_station_id: 'MAM-05', mark_code: '耳标-12', sex: '雄 / 雌 / 未知',
  life_stage: '成体 / 幼体', release_status: '释放 / 保留 / 逃脱',
  sample_collected: '毛发 / 粪便 / 血液 / 无', camera_station_id: 'HERP-CAM-02',
  camera_action: '布设 / 检查 / 回收', camera_model: 'HC550M',
  sensor_mode: '红外感应 / 延时拍摄', orientation: '东南 / 135°',
  bait_lure: '无 / 鱼油', media_file_id: 'IMG_0001', sequence_id: 'SEQ-12',
  quadrat_code: 'Q-01', vegetation_layer: '乔木层 / 灌木层 / 草本层',
  cover_percent: '30', phenology: '花期 / 果期 / 营养期',
  segment_length_m: '100', transect_width_m: '5', growth_form: '乔木 / 灌木 / 藤本 / 草本',
  weather_window: '晴朗微风', pace_note: '匀速行走',
  behavior_code: '飞行 / 晒太阳 / 取食', precipitation_code: '无 / 小雨 / 中雨',
  wind_code: '0-5', cloud_code: '0-10',
}

export function localizeLabel(key, locale) {
  if (locale === 'zh' && FIELD_LABELS_ZH[key]) return FIELD_LABELS_ZH[key]
  return humanizeFieldKey(key)
}

export function localizePlaceholder(key, locale) {
  if (locale === 'zh' && FIELD_PLACEHOLDERS_ZH[key]) return FIELD_PLACEHOLDERS_ZH[key]
  return ''
}

export function localizeOption(option, locale) {
  if (locale !== 'zh' || !option) return option
  return {
    ...option,
    label: option.label_zh || option.label,
    description: option.description_zh || option.description,
    shellLabel: option.shellLabel_zh || option.shellLabel,
    assetLabel: option.assetLabel_zh || option.assetLabel,
    assetHint: option.assetHint_zh || option.assetHint,
  }
}

export function localizeField(field, locale) {
  if (locale !== 'zh' || !field) return field
  return {
    ...field,
    label: FIELD_LABELS_ZH[field.key] || field.label,
    placeholder: FIELD_PLACEHOLDERS_ZH[field.key] || field.placeholder,
    options: field.options
      ? field.options.map((o) => (typeof o === 'string' ? o : { ...o, label: o.label_zh || o.label }))
      : undefined,
  }
}

export function localizeProtocol(protocol, locale) {
  if (locale !== 'zh' || !protocol) return protocol
  const localized = localizeOption(protocol, locale)
  return {
    ...localized,
    eventFields: (localized.eventFields || []).map((f) => localizeField(f, locale)),
    recordFields: (localized.recordFields || []).map((f) => localizeField(f, locale)),
  }
}

export function humanizeFieldKey(key = '') {
  return String(key || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (token) => token.toUpperCase())
}

export function uniqueNormalizedStrings(values = []) {
  return Array.from(new Set(
    values
      .flatMap((value) => (Array.isArray(value) ? value : [value]))
      .map((value) => String(value || '').trim())
      .filter(Boolean),
  ))
}

export function inferProtocolDefaultTaxonGroup(protocolId = '', fallback = '') {
  if (fallback) return fallback
  if (protocolId.startsWith('bird_')) return 'birds'
  if (protocolId === 'mammal_trap_net') return 'mammals'
  if (protocolId === 'herp_infrared_camera') return 'amphibians'
  if (protocolId.startsWith('plant_')) return 'plants'
  if (protocolId === 'insect_transect') return 'insects'
  return ''
}

export function inferProtocolDefaultEvidenceType(protocolId = '', fallback = 'visual') {
  if (fallback) return fallback
  if (protocolId === 'bird_point_count') return 'audio'
  if (protocolId === 'mammal_trap_net') return 'trace'
  return 'visual'
}

export function getVertebrateSubmoduleById(submoduleId = '') {
  return VERTEBRATE_SUBMODULES.find((item) => item.id === submoduleId) || VERTEBRATE_SUBMODULES[0]
}

export function resolveVertebrateSubmodule(submoduleId = '', taxonGroup = '', protocolId = '') {
  if (VERTEBRATE_SUBMODULES.some((item) => item.id === submoduleId)) return submoduleId
  if (VERTEBRATE_SUBMODULES.some((item) => item.id === taxonGroup)) return taxonGroup
  if (protocolId.startsWith('bird_')) return 'birds'
  if (protocolId === 'mammal_trap_net') return 'mammals'
  if (protocolId === 'herp_infrared_camera') {
    if (taxonGroup === 'reptiles') return 'reptiles'
    if (taxonGroup === 'amphibians') return 'amphibians'
  }
  return ''
}

export function deriveVertebrateSubmoduleId(submoduleId = '', taxonGroup = '', protocolId = '') {
  return resolveVertebrateSubmodule(submoduleId, taxonGroup, protocolId) || 'birds'
}

export function inferFieldType(fieldKey = '', fallbackField = null) {
  if (fallbackField?.type) return fallbackField.type
  if (/(^|_)(count|index|percent|radius|distance|length|duration|width|height|mass|area|days|nights|min|hour|hours|h|m|cm|mm|g|kg|c|s)$/.test(fieldKey)) {
    return 'number'
  }
  return 'text'
}

export function getRemoteFieldKeys(fieldGroups = {}) {
  return [
    ...toArray(fieldGroups.required),
    ...toArray(fieldGroups.optional),
    ...toArray(fieldGroups.effort),
  ]
}

export function buildProtocolFieldDefinitions(fieldGroups = {}, fallbackFields = [], { includeFallbackExtras = true } = {}) {
  const fallbackByKey = new Map(toArray(fallbackFields).map((field) => [field.key, field]))
  const requiredKeys = new Set(toArray(fieldGroups.required))
  const orderedKeys = includeFallbackExtras
    ? [
        ...toArray(fallbackFields).map((field) => field.key),
        ...getRemoteFieldKeys(fieldGroups),
      ]
    : getRemoteFieldKeys(fieldGroups)

  const seenKeys = new Set()
  const fields = []

  orderedKeys.forEach((fieldKey) => {
    if (!fieldKey || seenKeys.has(fieldKey)) return
    const fallbackField = fallbackByKey.get(fieldKey) || null
    fields.push({
      key: fieldKey,
      label: fallbackField?.label || humanizeFieldKey(fieldKey),
      type: inferFieldType(fieldKey, fallbackField),
      placeholder: fallbackField?.placeholder || humanizeFieldKey(fieldKey),
      required: requiredKeys.has(fieldKey) || Boolean(fallbackField?.required && !requiredKeys.size),
    })
    seenKeys.add(fieldKey)
  })

  if (fields.length === 0) {
    return toArray(fallbackFields).map((field) => ({ ...field }))
  }

  return fields
}

export function normalizeProtocolDefinition(protocolDefinition = {}, fallbackDefinition = null) {
  const protocolId = protocolDefinition.protocol_id || protocolDefinition.protocol || fallbackDefinition?.id || ''
  const program = protocolDefinition.program || fallbackDefinition?.program || ''
  const label = protocolDefinition.display_name || protocolDefinition.label || fallbackDefinition?.label || protocolId
  const designAssetTypes = toArray(protocolDefinition.design_asset_types)
  const trackPolicy = String(protocolDefinition.track_policy || '').trim().toLowerCase()
  const inferredSupportsTrack = trackPolicy
    ? !['none', 'disabled', 'unsupported', 'not_supported'].includes(trackPolicy)
    : undefined
  const fallbackVertebrateSubmodules = toArray(fallbackDefinition?.vertebrateSubmodules)
  const fallbackAllowedTaxonGroups = toArray(fallbackDefinition?.allowedTaxonGroups)
  const defaultTaxonGroup = inferProtocolDefaultTaxonGroup(protocolId, fallbackDefinition?.defaultTaxonGroup || '')

  return {
    ...fallbackDefinition,
    ...protocolDefinition,
    id: protocolId,
    protocol: protocolId,
    protocol_id: protocolId,
    program,
    label,
    display_name: label,
    shellLabel: fallbackDefinition?.shellLabel || label,
    description: protocolDefinition.description || fallbackDefinition?.description || '',
    assetLabel: fallbackDefinition?.assetLabel || 'Design asset',
    assetHint: fallbackDefinition?.assetHint || 'Select the matching design asset for this protocol.',
    requiresAsset: typeof protocolDefinition.requires_asset === 'boolean'
      ? protocolDefinition.requires_asset
      : (fallbackDefinition?.requiresAsset ?? designAssetTypes.length > 0),
    supportsTrack: typeof protocolDefinition.supports_track === 'boolean'
      ? protocolDefinition.supports_track
      : (typeof inferredSupportsTrack === 'boolean' ? inferredSupportsTrack : Boolean(fallbackDefinition?.supportsTrack)),
    defaultTaxonGroup,
    allowedTaxonGroups: fallbackAllowedTaxonGroups.length > 0 ? fallbackAllowedTaxonGroups : [defaultTaxonGroup].filter(Boolean),
    defaultEvidenceType: inferProtocolDefaultEvidenceType(protocolId, fallbackDefinition?.defaultEvidenceType || ''),
    vertebrateSubmodules: fallbackVertebrateSubmodules.length > 0 ? fallbackVertebrateSubmodules : [],
    jurisdictions: toArray(protocolDefinition.jurisdictions),
    design_asset_types: designAssetTypes,
    eventFieldGroups: protocolDefinition.event_fields || { required: toArray(protocolDefinition.required_event_fields) },
    recordFieldGroups: protocolDefinition.record_fields || { required: toArray(protocolDefinition.required_record_fields) },
    eventFields: buildProtocolFieldDefinitions(
      protocolDefinition.event_fields || { required: toArray(protocolDefinition.required_event_fields) },
      fallbackDefinition?.eventFields,
      { includeFallbackExtras: !protocolDefinition.has_structured_event_fields },
    ),
    recordFields: buildProtocolFieldDefinitions(
      protocolDefinition.record_fields || { required: toArray(protocolDefinition.required_record_fields) },
      fallbackDefinition?.recordFields,
      { includeFallbackExtras: !protocolDefinition.has_structured_record_fields },
    ),
  }
}

export function buildProtocolCatalog(protocolDefinitions = []) {
  const remoteDefinitions = toArray(protocolDefinitions)
  const remoteById = new Map(
    remoteDefinitions
      .map((definition) => [definition.protocol_id || definition.protocol || '', definition])
      .filter(([protocolId]) => Boolean(protocolId)),
  )

  return PROTOCOL_OPTIONS.map((fallbackDefinition) => (
    normalizeProtocolDefinition(remoteById.get(fallbackDefinition.id) || {}, fallbackDefinition)
  ))
}

export function mergeTaxonomyCatalogEntries(...catalogs) {
  const merged = new Map()
  catalogs.forEach((catalog) => {
    toArray(catalog).forEach((item) => {
      if (!item) return
      const key = item.internal_taxon_id || item.taxon_id || item.species_id || item.scientific_name || item.display_name
      if (!key) return
      merged.set(key, { ...(merged.get(key) || {}), ...item })
    })
  })
  return Array.from(merged.values())
}

export function findSpeciesMatch(speciesCatalog, rawValue) {
  const query = String(rawValue || '').trim().toLowerCase()
  if (!query) return null
  return (speciesCatalog || []).find((item) => {
    const names = uniqueNormalizedStrings([
      item?.scientific,
      item?.scientific_name,
      item?.english,
      item?.english_name,
      item?.chinese,
      item?.chinese_name,
      item?.display_name,
      item?.chinese_names,
      item?.english_names,
      item?.scientific_names,
      item?.synonyms,
      item?.names?.zh_cn,
      item?.names?.zh_tw,
      item?.names?.en,
      item?.names?.scientific,
      item?.names?.synonyms,
    ])
    return names.some((name) => String(name || '').trim().toLowerCase() === query)
  }) || null
}

export function createEmptyTransectSession(observer = '') {
  return {
    route_id: '',
    observer,
    weather: '',
    notes: '',
    started_at: '',
    ended_at: '',
  }
}

export function buildProtocolFieldState(fields = []) {
  return fields.reduce((accumulator, field) => {
    accumulator[field.key] = ''
    return accumulator
  }, {})
}

export function getProtocolDefinition(protocolId, protocolCatalog = PROTOCOL_OPTIONS) {
  return toArray(protocolCatalog).find((item) => item.id === protocolId) || toArray(protocolCatalog)[0] || PROTOCOL_OPTIONS[0]
}

export function createProtocolState(protocolId = PROTOCOL_OPTIONS[0].id, protocolCatalog = PROTOCOL_OPTIONS) {
  const definition = getProtocolDefinition(protocolId, protocolCatalog)
  return {
    program: definition.program,
    protocol: definition.id,
    event: buildProtocolFieldState(definition.eventFields),
    record: buildProtocolFieldState(definition.recordFields),
  }
}

export function resolveProtocolSelection(programId, protocolId = '', protocolCatalog = PROTOCOL_OPTIONS) {
  const catalog = toArray(protocolCatalog).length > 0 ? protocolCatalog : PROTOCOL_OPTIONS
  const preferred = catalog.find((item) => item.id === protocolId && item.program === programId)
  if (preferred) return preferred
  return catalog.find((item) => item.program === programId) || catalog[0] || PROTOCOL_OPTIONS[0]
}

export function normalizeProtocolFieldValues(fields = [], values = {}) {
  return fields.reduce((accumulator, field) => {
    const rawValue = values[field.key]
    if (rawValue == null || rawValue === '') return accumulator
    if (field.type === 'number') {
      const numeric = Number(rawValue)
      accumulator[field.key] = Number.isFinite(numeric) ? numeric : rawValue
      return accumulator
    }
    accumulator[field.key] = rawValue
    return accumulator
  }, {})
}

export function matchesActiveSubmodule(record, protocolDefinition, activeSubmoduleId = '') {
  if (protocolDefinition?.program !== 'terrestrial_vertebrates' || !activeSubmoduleId) return true
  const supportedSubmodules = toArray(record?.submodules)
  if (supportedSubmodules.length > 0) {
    return supportedSubmodules.includes(activeSubmoduleId)
  }
  const recordProtocol = record?.extra?.protocol || record?.protocol || ''
  const recordSubmodule = resolveVertebrateSubmodule(
    record?.extra?.submodule || record?.filters?.submodule || record?.submodule || '',
    record?.taxon_group || '',
    recordProtocol,
  )
  return !recordSubmodule || recordSubmodule === activeSubmoduleId
}

export function matchesProtocolObservation(record, protocolDefinition, activeSubmoduleId = '') {
  if (!record || !protocolDefinition) return false
  const recordProtocol = record?.extra?.protocol || record?.protocol || ''
  if (recordProtocol) {
    if (recordProtocol !== protocolDefinition.id) return false
    return matchesActiveSubmodule(record, protocolDefinition, activeSubmoduleId)
  }
  if (protocolDefinition.defaultTaxonGroup === 'insects') return record.taxon_group === 'insects'
  if (protocolDefinition.program === 'plants') return record.taxon_group === 'plants'
  if (protocolDefinition.id.startsWith('bird_')) return record.taxon_group === 'birds'
  if (protocolDefinition.id === 'mammal_trap_net') return record.taxon_group === 'mammals'
  if (protocolDefinition.id === 'herp_infrared_camera') {
    return ['amphibians', 'reptiles'].includes(record.taxon_group) && matchesActiveSubmodule(record, protocolDefinition, activeSubmoduleId)
  }
  return true
}

export function matchesProtocolTrack(record, protocolDefinition, activeSubmoduleId = '') {
  if (!record || !protocolDefinition) return false
  const recordProtocol = record?.extra?.protocol || record?.protocol || ''
  if (recordProtocol) {
    if (recordProtocol !== protocolDefinition.id) return false
    return matchesActiveSubmodule(record, protocolDefinition, activeSubmoduleId)
  }
  return matchesActiveSubmodule(record, protocolDefinition, activeSubmoduleId)
}

export function getMatchingTaxonomyPackages(packages, protocolDefinition, jurisdiction, activeSubmoduleId = '') {
  return toArray(packages)
    .filter((item) => (item.program || '') === protocolDefinition.program)
    .filter((item) => (item.jurisdiction || '') === jurisdiction)
    .filter((item) => {
      const supportedProtocols = toArray(item.protocols)
      return supportedProtocols.length === 0 || supportedProtocols.includes(protocolDefinition.id)
    })
    .filter((item) => matchesActiveSubmodule(item, protocolDefinition, activeSubmoduleId))
}

export function getTaxonomyGateIssueLabels(status, locale) {
  const isZh = locale === 'zh'
  const issues = []
  if (!status?.activePackage) issues.push(isZh ? '未固定分类包' : 'no taxonomy package is pinned')
  if (status?.activePackage && status.hasRequiredGateMetadata === false) issues.push(isZh ? '发布元数据不完整' : 'release metadata is incomplete')
  if (status?.hasCurrentReleaseIssue) issues.push(isZh ? '发布元数据非最新' : 'release metadata is not current')
  if (status?.hasChecksumMismatch) issues.push(isZh ? '校验和不匹配' : 'checksum metadata does not match')
  if (status?.hasParityIssue) issues.push(isZh ? '计数校验失败' : 'count parity failed')
  if (status?.hasReviewIssue) issues.push(isZh ? '审核状态未通过' : 'review status is not approved')
  return issues
}

export function buildTaxonomyGateWarningMessage(status, locale) {
  if (!status?.isBlocked) return ''
  const isZh = locale === 'zh'
  const packageLabel = (isZh && status.activePackage?.label_zh)
    || status.activePackage?.label
    || status.activePackage?.package_id
    || status.activePackage?.taxonomy_release_id
    || (isZh ? '当前分类包' : 'The active taxonomy package')
  const issues = getTaxonomyGateIssueLabels(status, locale)
  if (issues.length === 0) return ''
  return isZh
    ? `${packageLabel} 因以下原因被阻止导出：${issues.join('、')}。请拉取最新元数据或刷新缓存包后重试。`
    : `${packageLabel} is blocked for release export because ${issues.join(', ')}. Pull the latest metadata or refresh the cached package before exporting.`
}

export function buildTaxonomyMetricNote(status, locale) {
  const isZh = locale === 'zh'
  if (!status?.activePackage) return isZh ? '请拉取调查元数据以固定离线分类包' : 'Pull survey metadata to pin an offline package'
  const issues = getTaxonomyGateIssueLabels(status, locale)
  if (issues.length > 0) return issues.join(' | ')
  return status.activePackage.package_id || status.activePackage.taxonomy_release_id || (isZh ? '缓存包就绪' : 'Cached package ready')
}

export function buildTaxonomyGateBlockingMessage(status, protocolDefinition, jurisdictionLabel, locale) {
  const isZh = locale === 'zh'
  const issues = getTaxonomyGateIssueLabels(status, locale)
  if (issues.length === 0) return ''
  const packageLabel = (isZh && status.activePackage?.label_zh)
    || status.activePackage?.label
    || status.activePackage?.package_id
    || status.activePackage?.taxonomy_release_id
    || (isZh ? '当前分类包' : 'active taxonomy package')
  return isZh
    ? `${jurisdictionLabel} ${protocolDefinition.label} 导出被阻止，因为 ${packageLabel} 存在发布门控问题：${issues.join('、')}。`
    : `The ${jurisdictionLabel} ${protocolDefinition.label.toLowerCase()} export is blocked because ${packageLabel} has release-gating issues: ${issues.join(', ')}.`
}
