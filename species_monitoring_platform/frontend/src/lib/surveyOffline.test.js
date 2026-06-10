import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  collectAppliedSyncKeys,
  collectConflictSyncKeys,
  createDefaultProject,
  dedupeSyncOperations,
  deriveSurveyTaxonomyPackageStatus,
  emptySurveyState,
  loadSurveyState,
  mergeOutboxIntoState,
  mergeSyncPull,
  mergeStoredSurveyState,
  normalizeJurisdiction,
  replaceEntity,
  saveSurveyState,
  upsertLocalEntity,
} from "./surveyOffline";
import { resolveDraftAttachments } from "./fieldOpsDrafts";

describe("survey offline state helpers", () => {
  beforeEach(() => {
    const storage = new Map();
    globalThis.window = {
      localStorage: {
        getItem(key) {
          return storage.has(key) ? storage.get(key) : null;
        },
        setItem(key, value) {
          storage.set(key, String(value));
        },
        removeItem(key) {
          storage.delete(key);
        },
        clear() {
          storage.clear();
        },
      },
    };
  });

  afterEach(() => {
    delete globalThis.window;
  });

  it("normalizes legacy mainland jurisdiction aliases", () => {
    expect(normalizeJurisdiction("china_mainland")).toBe("mainland_china");
    expect(normalizeJurisdiction("mainland_china")).toBe("mainland_china");
  });

  it("keeps active jurisdiction normalized when merging stored state", () => {
    const merged = mergeStoredSurveyState(emptySurveyState(), {
      activeJurisdiction: "china_mainland",
    });

    expect(merged.activeJurisdiction).toBe("mainland_china");
  });

  it("does not auto-select the first stored route during restore", () => {
    const merged = mergeStoredSurveyState(emptySurveyState(), {
      routes: [
        {
          route_id: "route-1",
          project_id: "project-1",
          site_id: "site-1",
          updated_at: "2026-04-23T00:00:00Z",
        },
      ],
    });

    expect(merged.activeRouteId).toBe("");
  });

  it("preserves the restored active event selection", () => {
    const merged = mergeStoredSurveyState(emptySurveyState(), {
      events: [
        {
          event_id: "event-1",
          program: "plants",
          protocol: "plant_quadrat",
          updated_at: "2026-04-23T00:00:00Z",
        },
      ],
      activeEventId: "event-1",
    });

    expect(merged.activeEventId).toBe("event-1");
  });

  it("normalizes queued entity jurisdiction payloads before sync", () => {
    const nextState = upsertLocalEntity(emptySurveyState(), "event", {
      jurisdiction: "china_mainland",
      program: "plants",
      protocol: "plant_quadrat",
    });

    expect(nextState.activeJurisdiction).toBe("mainland_china");
    expect(nextState.syncQueue[0].payload.jurisdiction).toBe("mainland_china");
  });

  it("can promote a saved event to the active selection explicitly", () => {
    const state = {
      ...emptySurveyState(),
      activeEventId: "event-1",
      events: [
        {
          event_id: "event-1",
          program: "plants",
          protocol: "plant_quadrat",
          updated_at: "2026-04-22T00:00:00Z",
        },
      ],
    };

    const nextState = upsertLocalEntity(
      state,
      "event",
      {
        event_id: "event-2",
        program: "plants",
        protocol: "plant_quadrat",
        updated_at: "2026-04-23T00:00:00Z",
      },
      { select: true },
    );

    expect(nextState.activeEventId).toBe("event-2");
  });

  it("keeps the selected vertebrate submodule when a selected event is upserted", () => {
    const nextState = upsertLocalEntity(
      emptySurveyState(),
      "event",
      {
        event_id: "event-herp-reptile",
        program: "terrestrial_vertebrates",
        protocol: "herp_infrared_camera",
        submodule: "reptiles",
        updated_at: "2026-04-23T00:00:00Z",
      },
      { select: true },
    );

    expect(nextState.activeEventId).toBe("event-herp-reptile");
    expect(nextState.activeVertebrateSubmodule).toBe("reptiles");
  });

  it("selects an event when replacing it from a synced response", () => {
    const nextState = replaceEntity(
      emptySurveyState(),
      "event",
      {
        event_id: "event-synced",
        program: "plants",
        protocol: "plant_quadrat",
        updated_at: "2026-04-23T00:00:00Z",
      },
      { select: true },
    );

    expect(nextState.activeEventId).toBe("event-synced");
  });

  it("hydrates the active vertebrate submodule from sync pull metadata", () => {
    const merged = mergeSyncPull(emptySurveyState(), {
      active_program: "terrestrial_vertebrates",
      active_protocol: "herp_infrared_camera",
      active_vertebrate_submodule: "amphibians",
      pulled_at: "2026-04-23T00:00:00Z",
    });

    expect(merged.activeProgram).toBe("terrestrial_vertebrates");
    expect(merged.activeProtocol).toBe("herp_infrared_camera");
    expect(merged.activeVertebrateSubmodule).toBe("amphibians");
  });

  it("normalizes taxonomy release metadata during sync pull and keeps it in offline state", () => {
    const merged = mergeSyncPull(emptySurveyState(), {
      taxonomy_packages: [
        {
          taxonomy_release_id: "tw-2026-spring",
          source_manifest_version: "2026.04.20",
          imported_count: "1505",
          expected_count: 1505,
          count_parity_ok: "true",
          review_status: "approved",
          is_current_release: 1,
          checksum: "sha256:abc123",
          jurisdiction: "taiwan",
          program: "terrestrial_vertebrates",
        },
      ],
      pulled_at: "2026-04-23T00:00:00Z",
    });

    expect(merged.taxonomyPackages).toHaveLength(1);
    expect(merged.taxonomyPackages[0]).toMatchObject({
      package_id: "tw-2026-spring",
      taxonomy_release_id: "tw-2026-spring",
      source_manifest_version: "2026.04.20",
      expected_count: 1505,
      imported_count: 1505,
      count_parity_ok: true,
      review_status: "approved",
      is_current_release: true,
      checksum: "sha256:abc123",
    });
  });

  it("persists the stronger attachment contract and event linkage metadata", () => {
    saveSurveyState({
      ...emptySurveyState(),
      activeEventId: "event-1",
      activeDraftAttachmentIds: ["att-1"],
      mediaInbox: [
        {
          media_id: "att-1",
          name: "night-heron.jpg",
          type: "image/jpeg",
          size: 2048,
          local_uri: "blob://preview",
          storage_kind: "indexeddb",
          storage_key: "att-1",
        },
      ],
    });

    const restored = loadSurveyState();
    expect(restored.activeDraftAttachmentIds).toEqual(["att-1"]);
    expect(restored.mediaInbox[0]).toMatchObject({
      attachment_id: "att-1",
      media_id: "att-1",
      event_id: "event-1",
      owner_type: "event",
      owner_id: "event-1",
      mime_type: "image/jpeg",
      filename: "night-heron.jpg",
      byte_size: 2048,
      storage_key: "att-1",
      sync_state: "local_only",
    });
    expect(restored.mediaInbox[0].local_uri).toBeUndefined();
  });

  it("preserves taxonomy release and checksum metadata through local storage save and restore", () => {
    saveSurveyState({
      ...emptySurveyState(),
      taxonomyPackages: [
        {
          taxonomy_release_id: "cn-2026-q2",
          manifest_version: "manifest-v4",
          expected_species_count: "3201",
          imported_species_count: "3200",
          counts_match: "false",
          review_status: "needs_review",
          current: "yes",
          package_checksum: "sha256:def456",
          program: "plants",
          jurisdiction: "mainland_china",
        },
      ],
    });

    const restored = loadSurveyState();
    expect(restored.taxonomyPackages).toHaveLength(1);
    expect(restored.taxonomyPackages[0]).toMatchObject({
      package_id: "cn-2026-q2",
      taxonomy_release_id: "cn-2026-q2",
      source_manifest_version: "manifest-v4",
      expected_count: 3201,
      imported_count: 3200,
      count_parity_ok: false,
      review_status: "needs_review",
      is_current_release: true,
      checksum: "sha256:def456",
      program: "plants",
      jurisdiction: "mainland_china",
    });
  });

  it("preserves current release checksum metadata through local storage save and restore", () => {
    saveSurveyState({
      ...emptySurveyState(),
      taxonomyPackages: [
        {
          package_id: "tw-seed-v2",
          taxonomy_release_id: "tw-2026-summer",
          checksum: "sha256:active456",
          current_taxonomy_release_id: "tw-2026-autumn",
          current_release_checksum: "sha256:current789",
          current_release_count_parity_ok: false,
          current_release_review_status: "needs_review",
          program: "terrestrial_vertebrates",
          jurisdiction: "taiwan",
        },
      ],
    });

    const restored = loadSurveyState();
    expect(restored.taxonomyPackages[0]).toMatchObject({
      package_id: "tw-seed-v2",
      taxonomy_release_id: "tw-2026-summer",
      checksum: "sha256:active456",
      current_taxonomy_release_id: "tw-2026-autumn",
      current_release_checksum: "sha256:current789",
      current_release_count_parity_ok: false,
      current_release_review_status: "needs_review",
    });
  });

  it("detects stale taxonomy release metadata when the cached package no longer matches the current release", () => {
    const status = deriveSurveyTaxonomyPackageStatus([
      {
        package_id: "cn-seed-v1",
        taxonomy_release_id: "cn-2026-q1",
        checksum: "sha256:old111",
        current_taxonomy_release_id: "cn-2026-q2",
        current_release_checksum: "sha256:new222",
        count_parity_ok: true,
        review_status: "approved",
        is_current_release: false,
      },
    ]);

    expect(status.activePackage?.package_id).toBe("cn-seed-v1");
    expect(status.hasReleaseMismatch).toBe(true);
    expect(status.hasChecksumMismatch).toBe(true);
    expect(status.hasCurrentReleaseIssue).toBe(true);
    expect(status.isBlocked).toBe(true);
    expect(status.reasonCodes).toEqual(["stale_release", "checksum_mismatch"]);
  });

  it("detects checksum conflicts after a sync pull restores duplicate release metadata with different checksums", () => {
    const status = deriveSurveyTaxonomyPackageStatus([
      {
        package_id: "tw-release-current",
        taxonomy_release_id: "tw-2026-spring",
        checksum: "sha256:abc123",
        count_parity_ok: true,
        review_status: "approved",
        is_current_release: true,
      },
      {
        package_id: "tw-release-restore",
        taxonomy_release_id: "tw-2026-spring",
        checksum: "sha256:legacy999",
        count_parity_ok: true,
        review_status: "approved",
      },
    ]);

    expect(status.activePackage?.package_id).toBe("tw-release-current");
    expect(status.isCurrentRelease).toBe(true);
    expect(status.hasChecksumMismatch).toBe(true);
    expect(status.isBlocked).toBe(true);
    expect(status.reasonCodes).toEqual(["checksum_mismatch"]);
  });

  it("blocks exports when no taxonomy package has been pinned for the active scope", () => {
    const status = deriveSurveyTaxonomyPackageStatus([]);

    expect(status.activePackage).toBeNull();
    expect(status.isBlocked).toBe(true);
    expect(status.reasonCodes).toEqual(["missing_package"]);
  });

  it("blocks exports when release metadata is incomplete even if no explicit mismatch is reported yet", () => {
    const status = deriveSurveyTaxonomyPackageStatus([
      {
        package_id: "cn-release-incomplete",
        taxonomy_release_id: "cn-2026-q3",
        program: "plants",
        jurisdiction: "mainland_china",
        is_current_release: true,
      },
    ]);

    expect(status.activePackage?.package_id).toBe("cn-release-incomplete");
    expect(status.hasRequiredGateMetadata).toBe(false);
    expect(status.isBlocked).toBe(true);
    expect(status.reasonCodes).toEqual(["missing_gate_metadata"]);
  });

  it("restores draft attachments by attachment_id while remaining media_id compatible", () => {
    const restored = resolveDraftAttachments(
      [
        { attachment_id: "att-1", media_id: "att-1", filename: "first.jpg" },
        { media_id: "legacy-2", name: "legacy.wav" },
      ],
      ["legacy-2", "att-1", "missing"],
    );

    expect(restored).toEqual([
      { media_id: "legacy-2", name: "legacy.wav" },
      { attachment_id: "att-1", media_id: "att-1", filename: "first.jpg" },
    ]);
  });

  it("creates a clean default biodiversity field project", () => {
    const project = createDefaultProject({
      study_region: {
        name: "Taiwan Highlands",
      },
    });

    expect(project.name).toBe("Taiwan Highlands Field Survey");
    expect(project.region).toBe("Taiwan Highlands");
    expect(project.jurisdiction).toBe("mainland_china");
  });
});

describe("B24 sync outbox helpers", () => {
  it("dedupes combined queue + outbox ops per entity, keeping the newest", () => {
    const ops = dedupeSyncOperations([
      {
        op_id: "op_state",
        entity_type: "project",
        operation: "upsert",
        entity_id: "proj-1",
        payload: { name: "old" },
        queued_at: "2026-06-10T01:00:00Z",
      },
      {
        op_id: "op_outbox",
        entity_type: "project",
        operation: "upsert",
        entity_id: "proj-1",
        payload: { name: "new" },
        queued_at: "2026-06-10T02:00:00Z",
      },
      {
        op_id: "op_other",
        entity_type: "site",
        operation: "upsert",
        entity_id: "site-1",
        payload: {},
        queued_at: "2026-06-10T01:30:00Z",
      },
    ]);

    expect(ops).toHaveLength(2);
    const project = ops.find((op) => op.entity_id === "proj-1");
    expect(project.op_id).toBe("op_outbox");
    expect(project.payload.name).toBe("new");
  });

  it("keeps upsert and delete ops for the same entity as distinct operations", () => {
    const ops = dedupeSyncOperations([
      {
        op_id: "op_upsert",
        entity_type: "observation",
        operation: "upsert",
        entity_id: "obs-1",
        payload: {},
        queued_at: "2026-06-10T01:00:00Z",
      },
      {
        op_id: "op_delete",
        entity_type: "observation",
        operation: "delete",
        entity_id: "obs-1",
        payload: {},
        queued_at: "2026-06-10T02:00:00Z",
      },
    ]);

    expect(ops).toHaveLength(2);
    expect(ops.map((op) => op.operation).sort()).toEqual([
      "delete",
      "upsert",
    ]);
  });

  it("resolves entity type aliases while deduping", () => {
    const ops = dedupeSyncOperations([
      {
        op_id: "op_alias",
        entity_type: "sampling_event",
        operation: "upsert",
        entity_id: "evt-1",
        payload: {},
        queued_at: "2026-06-10T01:00:00Z",
      },
      {
        op_id: "op_canonical",
        entity_type: "event",
        operation: "upsert",
        entity_id: "evt-1",
        payload: {},
        queued_at: "2026-06-10T02:00:00Z",
      },
    ]);

    expect(ops).toHaveLength(1);
    expect(ops[0].entity_type).toBe("event");
    expect(ops[0].op_id).toBe("op_canonical");
  });

  it("merges outbox rows into surveyState.syncQueue without duplicating entities", () => {
    const seeded = upsertLocalEntity(emptySurveyState(), "project", {
      project_id: "proj-9",
      name: "From state",
    });
    expect(seeded.syncQueue).toHaveLength(1);

    const merged = mergeOutboxIntoState(seeded, [
      {
        op_id: "op_box1",
        entity_type: "project",
        operation: "upsert",
        entity_id: "proj-9",
        payload: { project_id: "proj-9", name: "From outbox (newer)" },
        queued_at: "2999-01-01T00:00:00Z",
        queue_status: "pending",
      },
      {
        op_id: "op_box2",
        entity_type: "observation",
        operation: "delete",
        entity_id: "obs-7",
        payload: { observation_id: "obs-7" },
        queued_at: "2999-01-01T00:00:01Z",
        queue_status: "pending",
      },
    ]);

    expect(merged.syncQueue).toHaveLength(2);
    const projectOp = merged.syncQueue.find(
      (op) => op.entity_id === "proj-9",
    );
    expect(projectOp.op_id).toBe("op_box1");
    expect(
      merged.syncQueue.some(
        (op) => op.entity_id === "obs-7" && op.operation === "delete",
      ),
    ).toBe(true);
  });

  it("collects applied, deleted and conflict keys from a sync job", () => {
    const syncJob = {
      applied: [
        {
          entity_type: "project",
          record: { project_id: "proj-1", updated_at: "t1" },
        },
      ],
      deleted: [{ entity_type: "site", entity_id: "site-2" }],
      conflicts: [{ entity_type: "observation", entity_id: "obs-3" }],
    };

    expect(collectAppliedSyncKeys(syncJob).sort()).toEqual([
      "project:proj-1",
      "site:site-2",
    ]);
    expect(collectConflictSyncKeys(syncJob)).toEqual(["observation:obs-3"]);
  });
});
