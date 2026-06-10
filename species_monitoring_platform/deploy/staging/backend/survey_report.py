"""
Comprehensive Biodiversity Survey Report Generator

Produces structured reports from multimodal survey sessions combining
camera trap imagery, audio recordings, and manual field observations.

Supports CSV, JSON, and Darwin Core Archive export formats.
"""

import csv
import io
import json
import logging
import zipfile
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def generate_csv_report(session_summary: dict) -> str:
    """Generate a CSV species inventory from a survey summary."""
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Species", "Total Detections", "Image Detections", "Audio Detections",
        "Manual Observations", "Max Confidence", "Evidence Types",
        "Multimodal", "First Seen", "Last Seen",
    ])

    for sp in session_summary.get("species_list", []):
        writer.writerow([
            sp["species"],
            sp["total_detections"],
            sp["image_detections"],
            sp["audio_detections"],
            sp["manual_observations"],
            sp["max_confidence"],
            "; ".join(sp["evidence_types"]),
            "Yes" if sp["multimodal"] else "No",
            sp.get("first_seen", ""),
            sp.get("last_seen", ""),
        ])

    writer.writerow([])
    writer.writerow(["--- Survey Metadata ---"])
    for key in ["session_id", "site_name", "latitude", "longitude", "start_time", "end_time", "habitat_type", "observer"]:
        writer.writerow([key, session_summary.get(key, "")])

    diversity = session_summary.get("diversity", {})
    writer.writerow([])
    writer.writerow(["--- Diversity Indices ---"])
    for key, value in diversity.items():
        writer.writerow([key, value])

    return output.getvalue()


def generate_json_report(session_summary: dict) -> str:
    """Generate a detailed JSON report."""
    report = {
        "report_type": "multimodal_biodiversity_survey",
        "generated_at": datetime.now(UTC).isoformat(),
        "survey": {
            "session_id": session_summary.get("session_id"),
            "site": {
                "name": session_summary.get("site_name"),
                "latitude": session_summary.get("latitude"),
                "longitude": session_summary.get("longitude"),
                "habitat_type": session_summary.get("habitat_type"),
            },
            "time_range": {
                "start": session_summary.get("start_time"),
                "end": session_summary.get("end_time"),
            },
            "observer": session_summary.get("observer"),
        },
        "effort": {
            "total_images": session_summary.get("total_images", 0),
            "blank_images": session_summary.get("blank_images", 0),
            "effective_images": session_summary.get("total_images", 0) - session_summary.get("blank_images", 0),
            "total_audio_recordings": session_summary.get("total_audio", 0),
            "manual_observations": session_summary.get("total_manual", 0),
        },
        "results": {
            "total_species": session_summary.get("total_species", 0),
            "diversity_indices": session_summary.get("diversity", {}),
            "species_list": session_summary.get("species_list", []),
        },
    }
    return json.dumps(report, indent=2, ensure_ascii=False, default=str)


def generate_darwin_core_archive(
    session_summary: dict,
    output_path: Optional[str] = None,
) -> bytes:
    """Generate a Darwin Core Archive (DwC-A) ZIP file.

    Produces a standards-compliant archive with:
    - occurrence.csv (species occurrence records)
    - event.csv (sampling events)
    - meta.xml (archive descriptor)
    - eml.xml (dataset metadata)
    """
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        occurrence_csv = _build_dwc_occurrences(session_summary)
        zf.writestr("occurrence.csv", occurrence_csv)

        event_csv = _build_dwc_events(session_summary)
        zf.writestr("event.csv", event_csv)

        meta_xml = _build_dwc_meta_xml()
        zf.writestr("meta.xml", meta_xml)

        eml_xml = _build_dwc_eml(session_summary)
        zf.writestr("eml.xml", eml_xml)

    archive_bytes = buf.getvalue()

    if output_path:
        Path(output_path).write_bytes(archive_bytes)

    return archive_bytes


def _build_dwc_occurrences(summary: dict) -> str:
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "occurrenceID", "eventID", "scientificName", "individualCount",
        "occurrenceStatus", "basisOfRecord", "decimalLatitude",
        "decimalLongitude", "eventDate", "samplingProtocol",
        "occurrenceRemarks",
    ])

    event_id = summary.get("session_id", "")
    lat = summary.get("latitude", "")
    lon = summary.get("longitude", "")
    event_date = summary.get("start_time", "")
    if event_date and "T" in event_date:
        event_date = event_date.split("T")[0]

    for i, sp in enumerate(summary.get("species_list", []), 1):
        evidence = "; ".join(sp.get("evidence_types", []))
        protocol = "camera_trap+acoustic+manual" if sp.get("multimodal") else evidence

        writer.writerow([
            f"{event_id}-occ-{i:04d}",
            event_id,
            sp["species"],
            sp["total_detections"],
            "present",
            "MachineObservation" if sp["image_detections"] > 0 or sp["audio_detections"] > 0 else "HumanObservation",
            lat,
            lon,
            event_date,
            protocol,
            f"max_confidence={sp['max_confidence']}; img={sp['image_detections']}; audio={sp['audio_detections']}; manual={sp['manual_observations']}",
        ])

    return output.getvalue()


def _build_dwc_events(summary: dict) -> str:
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "eventID", "eventDate", "decimalLatitude", "decimalLongitude",
        "habitat", "samplingProtocol", "samplingEffort",
        "eventRemarks",
    ])

    start = summary.get("start_time", "")
    end = summary.get("end_time", "")
    event_date = start.split("T")[0] if start and "T" in start else start
    if end:
        end_date = end.split("T")[0] if "T" in end else end
        if end_date != event_date:
            event_date = f"{event_date}/{end_date}"

    effort_parts = []
    if summary.get("total_images"):
        effort_parts.append(f"{summary['total_images']} camera trap images")
    if summary.get("total_audio"):
        effort_parts.append(f"{summary['total_audio']} audio recordings")
    if summary.get("total_manual"):
        effort_parts.append(f"{summary['total_manual']} manual observations")

    writer.writerow([
        summary.get("session_id", ""),
        event_date,
        summary.get("latitude", ""),
        summary.get("longitude", ""),
        summary.get("habitat_type", ""),
        "multimodal: camera_trap + passive_acoustic_monitoring + visual_observation",
        "; ".join(effort_parts),
        f"observer={summary.get('observer', '')}",
    ])

    return output.getvalue()


def _build_dwc_meta_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<archive xmlns="http://rs.tdwg.org/dwc/text/"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://rs.tdwg.org/dwc/text/ http://rs.tdwg.org/dwc/text/tdwg_dwc_text.xsd">
  <core encoding="UTF-8" fieldsTerminatedBy="," linesTerminatedBy="\\n" fieldsEnclosedBy="&quot;" ignoreHeaderLines="1" rowType="http://rs.tdwg.org/dwc/terms/Occurrence">
    <files><location>occurrence.csv</location></files>
    <id index="0"/>
    <field index="1" term="http://rs.tdwg.org/dwc/terms/eventID"/>
    <field index="2" term="http://rs.tdwg.org/dwc/terms/scientificName"/>
    <field index="3" term="http://rs.tdwg.org/dwc/terms/individualCount"/>
    <field index="4" term="http://rs.tdwg.org/dwc/terms/occurrenceStatus"/>
    <field index="5" term="http://rs.tdwg.org/dwc/terms/basisOfRecord"/>
    <field index="6" term="http://rs.tdwg.org/dwc/terms/decimalLatitude"/>
    <field index="7" term="http://rs.tdwg.org/dwc/terms/decimalLongitude"/>
    <field index="8" term="http://rs.tdwg.org/dwc/terms/eventDate"/>
    <field index="9" term="http://rs.tdwg.org/dwc/terms/samplingProtocol"/>
    <field index="10" term="http://rs.tdwg.org/dwc/terms/occurrenceRemarks"/>
  </core>
  <extension encoding="UTF-8" fieldsTerminatedBy="," linesTerminatedBy="\\n" fieldsEnclosedBy="&quot;" ignoreHeaderLines="1" rowType="http://rs.tdwg.org/dwc/terms/Event">
    <files><location>event.csv</location></files>
    <coreid index="0"/>
    <field index="1" term="http://rs.tdwg.org/dwc/terms/eventDate"/>
    <field index="2" term="http://rs.tdwg.org/dwc/terms/decimalLatitude"/>
    <field index="3" term="http://rs.tdwg.org/dwc/terms/decimalLongitude"/>
    <field index="4" term="http://rs.tdwg.org/dwc/terms/habitat"/>
    <field index="5" term="http://rs.tdwg.org/dwc/terms/samplingProtocol"/>
    <field index="6" term="http://rs.tdwg.org/dwc/terms/samplingEffort"/>
    <field index="7" term="http://rs.tdwg.org/dwc/terms/eventRemarks"/>
  </extension>
</archive>"""


def _build_dwc_eml(summary: dict) -> str:
    site = summary.get("site_name", "Unknown Site")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<eml:eml xmlns:eml="eml://ecoinformatics.org/eml-2.1.1"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="eml://ecoinformatics.org/eml-2.1.1 eml.xsd"
         packageId="{summary.get('session_id', '')}" system="multimodal-survey">
  <dataset>
    <title>Multimodal Biodiversity Survey: {site}</title>
    <abstract>
      <para>Multimodal wildlife diversity survey combining infrared camera traps,
      passive acoustic monitoring, and manual field observations at {site}.
      Total species detected: {summary.get('total_species', 0)}.</para>
    </abstract>
    <additionalInfo>
      <para>Generated by Species Monitoring Platform</para>
    </additionalInfo>
  </dataset>
</eml:eml>"""
