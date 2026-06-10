import { describe, expect, it } from "vitest";
import {
  getApiErrorMessage,
  normalizeDeviceMarker,
  normalizeDeviceRecord,
  normalizeDeviceType,
  normalizeEmbeddingStats,
  normalizeHealthStatus,
  normalizeMonitoringDashboard,
  normalizeMonitoringSession,
  normalizeSurveyProtocolDefinition,
  normalizeSurveyTaxonomyEntry,
  normalizeSurveyTaxonomyPackage,
  resolveApiTransportConfig,
  resolveConfiguredApiBases,
} from "./api";
import {
  attachmentListsMatch,
  buildTrackDraftForStart,
  normalizeAttachmentIds,
  normalizeTrackDraft,
  resolveDraftAttachments,
} from "./fieldOpsDrafts";

describe("api helpers", () => {
  it("keeps the default api base unless a valid native override is available", () => {
    expect(resolveApiTransportConfig("", true)).toMatchObject({
      useNativeApiBase: false,
      apiBase: "/api",
      wsBase: null,
    });

    expect(
      resolveApiTransportConfig("https://field.example.com/platform", false),
    ).toMatchObject({
      useNativeApiBase: false,
      apiBase: "/api",
      wsBase: null,
    });

    expect(
      resolveApiTransportConfig("https://field.example.com/platform", true),
    ).toMatchObject({
      useNativeApiBase: true,
      apiBase: "https://field.example.com/platform/api",
      wsBase: "wss://field.example.com/platform/ws",
    });
  });

  it("normalizes configured absolute api bases for native clients", () => {
    expect(
      resolveConfiguredApiBases("https://field.example.com/platform/"),
    ).toEqual({
      apiBase: "https://field.example.com/platform/api",
      wsBase: "wss://field.example.com/platform/ws",
    });

    expect(
      resolveConfiguredApiBases("http://field.example.com/platform/api"),
    ).toEqual({
      apiBase: "http://field.example.com/platform/api",
      wsBase: "ws://field.example.com/platform/ws",
    });

    expect(resolveConfiguredApiBases("capacitor://localhost")).toBeNull();
    expect(resolveConfiguredApiBases("/relative/api")).toBeNull();
  });

  it("extracts readable API error messages", () => {
    expect(
      getApiErrorMessage(
        { response: { data: { detail: "Bad request" } } },
        "fallback",
      ),
    ).toBe("Bad request");
    expect(
      getApiErrorMessage(
        { response: { data: { detail: [{ msg: "Missing field" }] } } },
        "fallback",
      ),
    ).toBe("Missing field");
    expect(getApiErrorMessage({ message: "Network down" }, "fallback")).toBe(
      "Network down",
    );
    expect(getApiErrorMessage({}, "fallback")).toBe("fallback");
  });

  it("normalizes health payloads and derives warning runtime state", () => {
    const result = normalizeHealthStatus({
      num_species_model: 217,
      num_species_db: 254,
      warnings: [{ level: "warning", title: "Gap" }],
    });

    expect(result.runtime_state).toBe("warning");
    expect(result.species_coverage.missing_from_model).toBe(37);
    expect(result.species_coverage.coverage_ratio).toBeCloseTo(217 / 254);
  });

  it("normalizes device types to backend-safe values", () => {
    expect(normalizeDeviceType("AudioMoth")).toBe("audiomoth");
    expect(normalizeDeviceType("Raspberry Pi")).toBe("raspberry_pi");
    expect(normalizeDeviceType("Song Meter")).toBe("song_meter");
    expect(normalizeDeviceType("ARU")).toBe("generic");
    expect(normalizeDeviceType("Jetson")).toBe("generic");
  });

  it("normalizes device records and map markers for UI consumption", () => {
    expect(
      normalizeDeviceRecord({ device_type: "audiomoth", status: "recording" }),
    ).toMatchObject({
      type: "audiomoth",
      online: true,
    });
    expect(
      normalizeDeviceMarker({ lat: 22.4, lng: 106.9, status: "offline" }),
    ).toMatchObject({
      latitude: 22.4,
      longitude: 106.9,
      online: false,
    });
  });

  it("normalizes monitoring and embedding summaries", () => {
    expect(
      normalizeMonitoringSession({ unique_species: 5, total_detections: 12 }),
    ).toMatchObject({
      species_count: 5,
      detection_count: 12,
    });
    expect(
      normalizeMonitoringDashboard({
        sessions: { active: 0 },
        detections: { total: 7, unique_species: 3 },
      }),
    ).toMatchObject({
      total_detections: 7,
      unique_species: 3,
      mode: "idle",
    });
    expect(
      normalizeEmbeddingStats({ total_records: 9, dimensions: 512 }),
    ).toMatchObject({
      total_embeddings: 9,
      embedding_dim: 512,
    });
  });

  it("normalizes survey protocol payloads from both current and structured metadata shapes", () => {
    expect(
      normalizeSurveyProtocolDefinition({
        protocol: "bird_line_transect",
        label: "Bird line transect",
        required_event_fields: ["started_at", "ended_at"],
        required_record_fields: ["taxon_id_or_name", "count"],
      }),
    ).toMatchObject({
      protocol_id: "bird_line_transect",
      event_fields: {
        required: ["started_at", "ended_at"],
        optional: [],
        effort: [],
      },
      record_fields: {
        required: ["taxon_id_or_name", "count"],
        optional: [],
      },
      has_structured_event_fields: false,
      has_structured_record_fields: false,
    });

    expect(
      normalizeSurveyProtocolDefinition({
        protocol_id: "insect_transect",
        display_name: "Insect Transect Survey",
        event_fields: {
          required: ["transect_name"],
          optional: ["weather"],
          effort: ["distance_walked_m"],
        },
        record_fields: {
          required: ["taxon_id", "count"],
          optional: ["life_stage"],
        },
      }),
    ).toMatchObject({
      protocol_id: "insect_transect",
      display_name: "Insect Transect Survey",
      event_fields: {
        required: ["transect_name"],
        optional: ["weather"],
        effort: ["distance_walked_m"],
      },
      record_fields: {
        required: ["taxon_id", "count"],
        optional: ["life_stage"],
      },
      has_structured_event_fields: true,
      has_structured_record_fields: true,
    });
  });

  it("normalizes survey taxonomy entries into a consistent lookup contract", () => {
    expect(
      normalizeSurveyTaxonomyEntry({
        internal_taxon_id: "vert-reptile-cuora-flavomarginata",
        scientific_name: "Cuora flavomarginata",
        traditional_chinese_name: "食蛇龜",
        english_common_name: "Yellow-margined box turtle",
        synonyms: ["Cistoclemmys flavomarginata"],
        names: {
          zh_tw: "食蛇龜",
          en: "Yellow-margined box turtle",
        },
        group: "reptiles",
      }),
    ).toMatchObject({
      internal_taxon_id: "vert-reptile-cuora-flavomarginata",
      taxon_id: "vert-reptile-cuora-flavomarginata",
      scientific_name: "Cuora flavomarginata",
      chinese_name: "食蛇龜",
      english_name: "Yellow-margined box turtle",
      taxon_group: "reptiles",
      synonyms: ["Cistoclemmys flavomarginata"],
      display_name: "食蛇龜",
    });
  });

  it("normalizes survey taxonomy package metadata into a stable package contract", () => {
    expect(
      normalizeSurveyTaxonomyPackage({
        asset_package_id: "tw-vertebrates-v1",
        taxonomy_release_id: "tw-2026-spring",
        source_manifest_version: "2026.04.20",
        display_name: "Taiwan vertebrates",
        protocol: ["bird_point_count", "bird_line_transect"],
        jurisdiction: "taiwan",
        program: "terrestrial_vertebrates",
        expected_count: "1505",
        imported_count: 1505,
        count_parity_ok: "true",
        review_status: "approved",
        is_current_release: 1,
        checksum: "sha256:abc123",
        catalog_entry_count: 1505,
        exhaustive: true,
      }),
    ).toMatchObject({
      package_id: "tw-vertebrates-v1",
      taxonomy_package_id: "tw-vertebrates-v1",
      asset_package_id: "tw-vertebrates-v1",
      taxonomy_release_id: "tw-2026-spring",
      source_manifest_version: "2026.04.20",
      display_name: "Taiwan vertebrates",
      label: "Taiwan vertebrates",
      protocols: ["bird_point_count", "bird_line_transect"],
      jurisdiction: "taiwan",
      program: "terrestrial_vertebrates",
      expected_count: 1505,
      imported_count: 1505,
      count_parity_ok: true,
      review_status: "approved",
      is_current_release: true,
      checksum: "sha256:abc123",
      catalog_count: 1505,
      catalog_entry_count: 1505,
      exhaustive: true,
      exhaustive_species_content: true,
    });
  });

  it("falls back to release metadata aliases when package ids and booleans arrive in alternate shapes", () => {
    expect(
      normalizeSurveyTaxonomyPackage({
        release_id: "cn-2026-q2",
        manifest_version: "manifest-v4",
        protocols: "plant_quadrat",
        imported_species_count: "3200",
        expected_species_count: "3201",
        counts_match: "false",
        current: "yes",
        package_checksum: "sha256:def456",
      }),
    ).toMatchObject({
      package_id: "cn-2026-q2",
      taxonomy_package_id: "cn-2026-q2",
      asset_package_id: "cn-2026-q2",
      taxonomy_release_id: "cn-2026-q2",
      source_manifest_version: "manifest-v4",
      protocols: ["plant_quadrat"],
      imported_count: 3200,
      expected_count: 3201,
      count_parity_ok: false,
      is_current_release: true,
      checksum: "sha256:def456",
    });
  });

  it("preserves current release aliases without coercing missing gate metadata to false", () => {
    const normalized = normalizeSurveyTaxonomyPackage({
      asset_package_id: "tw-vertebrates-v2",
      taxonomy_release_id: "tw-2026-summer",
      checksum: "sha256:active456",
      current_taxonomy_release_id: "tw-2026-autumn",
      current_release: {
        checksum: "sha256:current789",
        taxonomy_count_parity_ok: false,
        review_status: "needs_review",
      },
    });

    expect(normalized).toMatchObject({
      package_id: "tw-vertebrates-v2",
      taxonomy_release_id: "tw-2026-summer",
      checksum: "sha256:active456",
      current_taxonomy_release_id: "tw-2026-autumn",
      current_release_checksum: "sha256:current789",
      current_release_count_parity_ok: false,
      current_release_review_status: "needs_review",
    });
    expect(normalized.count_parity_ok).toBeUndefined();
    expect(normalized.is_current_release).toBeUndefined();
  });

  it("leaves release gating fields undefined for legacy taxonomy package records", () => {
    const normalized = normalizeSurveyTaxonomyPackage({
      package_id: "legacy-seed",
      program: "plants",
      protocol: "plant_quadrat",
    });

    expect(normalized.package_id).toBe("legacy-seed");
    expect(normalized.count_parity_ok).toBeUndefined();
    expect(normalized.is_current_release).toBeUndefined();
    expect(normalized.current_release_count_parity_ok).toBeUndefined();
    expect(normalized.review_status).toBe("");
    expect(normalized.current_taxonomy_release_id).toBe("");
    expect(normalized.current_release_checksum).toBe("");
  });

  it("resumes paused track drafts only for the same route and preserves prior points", () => {
    const pausedDraft = normalizeTrackDraft({
      started_at: "2026-04-21T10:00:00.000Z",
      route_id: "route-1",
      route_name: "North Transect",
      observer: "Existing observer",
      points: [
        ["120.5", "30.2"],
        ["120.6", "30.3"],
      ],
      point_times: ["2026-04-21T10:00:00.000Z", "2026-04-21T10:05:00.000Z"],
      tracking_status: "paused",
      extra: { module: "pilot" },
    });

    expect(
      buildTrackDraftForStart({
        existingDraft: pausedDraft,
        selectedRoute: { route_id: "route-1", name: "North Transect" },
        observer: "  New observer  ",
        weather: "  cloudy ",
        notes: "  resumed ",
        extra: { module: "pilot", restarted: true },
        startedAt: "2026-04-22T10:00:00.000Z",
      }),
    ).toMatchObject({
      started_at: "2026-04-21T10:00:00.000Z",
      route_id: "route-1",
      route_name: "North Transect",
      observer: "New observer",
      weather: "cloudy",
      notes: "resumed",
      tracking_status: "recording",
      points: [
        [120.5, 30.2],
        [120.6, 30.3],
      ],
      point_times: ["2026-04-21T10:00:00.000Z", "2026-04-21T10:05:00.000Z"],
      extra: { module: "pilot", restarted: true },
    });

    expect(
      buildTrackDraftForStart({
        existingDraft: pausedDraft,
        selectedRoute: { route_id: "route-2", name: "South Transect" },
        observer: "New observer",
        startedAt: "2026-04-22T11:00:00.000Z",
      }),
    ).toMatchObject({
      started_at: "2026-04-22T11:00:00.000Z",
      route_id: "route-2",
      route_name: "South Transect",
      tracking_status: "recording",
      points: [],
      point_times: [],
    });
  });

  it("restores draft attachments in stored id order and ignores missing or duplicate ids", () => {
    const mediaInbox = [
      { media_id: "photo-1", name: "Photo 1" },
      { media_id: "audio-1", name: "Audio 1" },
      { media_id: "photo-2", name: "Photo 2" },
    ];

    const restored = resolveDraftAttachments(mediaInbox, [
      "audio-1",
      "photo-1",
      "missing",
      "audio-1",
      "",
      null,
    ]);

    expect(
      normalizeAttachmentIds(restored.map((item) => item.media_id)),
    ).toEqual(["audio-1", "photo-1"]);
    expect(restored).toEqual([
      { media_id: "audio-1", name: "Audio 1" },
      { media_id: "photo-1", name: "Photo 1" },
    ]);
    expect(
      attachmentListsMatch(["audio-1", "photo-1"], ["audio-1", "photo-1"]),
    ).toBe(true);
    expect(attachmentListsMatch(["audio-1"], ["photo-1"])).toBe(false);
  });
});
