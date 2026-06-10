import {
  getAttachmentLookupId,
  normalizeAttachmentIds,
} from "./attachmentContract";

export { normalizeAttachmentIds } from "./attachmentContract";

export function createEmptyTrackDraft() {
  return {
    points: [],
    point_times: [],
    started_at: "",
    route_id: "",
    observer: "",
    weather: "",
    notes: "",
    route_name: "",
    extra: {},
    tracking_status: "idle",
  };
}

export function attachmentListsMatch(left = [], right = []) {
  if (left.length !== right.length) return false;
  return left.every((value, index) => value === right[index]);
}

export function resolveDraftAttachments(mediaInbox = [], attachmentIds = []) {
  const normalizedIds = normalizeAttachmentIds(attachmentIds);
  if (normalizedIds.length === 0) return [];

  const mediaById = new Map(
    (Array.isArray(mediaInbox) ? mediaInbox : [])
      .map((item) => [getAttachmentLookupId(item), item])
      .filter(([attachmentId]) => attachmentId),
  );

  return normalizedIds
    .map((attachmentId) => mediaById.get(attachmentId))
    .filter(Boolean);
}

export function normalizeTrackDraft(draft) {
  if (!draft || typeof draft !== "object" || !draft.started_at) return null;

  return {
    ...createEmptyTrackDraft(),
    ...draft,
    points: Array.isArray(draft.points)
      ? draft.points
          .filter((point) => Array.isArray(point) && point.length >= 2)
          .map((point) => [Number(point[0]), Number(point[1])])
          .filter(
            (point) => Number.isFinite(point[0]) && Number.isFinite(point[1]),
          )
      : [],
    point_times: Array.isArray(draft.point_times)
      ? draft.point_times.filter((value) => typeof value === "string" && value)
      : [],
    route_id: typeof draft.route_id === "string" ? draft.route_id : "",
    observer: typeof draft.observer === "string" ? draft.observer : "",
    weather: typeof draft.weather === "string" ? draft.weather : "",
    notes: typeof draft.notes === "string" ? draft.notes : "",
    route_name: typeof draft.route_name === "string" ? draft.route_name : "",
    extra: draft.extra && typeof draft.extra === "object" ? draft.extra : {},
    tracking_status:
      draft.tracking_status === "paused" ? "paused" : "recording",
  };
}

export function buildTrackDraftForStart({
  existingDraft = null,
  selectedRoute = null,
  observer = "",
  weather = "",
  notes = "",
  extra = {},
  startedAt = "",
} = {}) {
  const normalizedExisting = normalizeTrackDraft(existingDraft);
  const routeId =
    typeof selectedRoute?.route_id === "string" ? selectedRoute.route_id : "";
  const shouldResumeExisting = Boolean(
    normalizedExisting && normalizedExisting.route_id === routeId,
  );

  return normalizeTrackDraft({
    ...(shouldResumeExisting ? normalizedExisting : createEmptyTrackDraft()),
    started_at: shouldResumeExisting
      ? normalizedExisting.started_at
      : startedAt,
    route_id: routeId,
    observer: String(observer || "").trim(),
    weather: String(weather || "").trim(),
    notes: String(notes || "").trim(),
    route_name:
      typeof selectedRoute?.name === "string" ? selectedRoute.name : "",
    extra: extra && typeof extra === "object" ? extra : {},
    tracking_status: "recording",
  });
}
