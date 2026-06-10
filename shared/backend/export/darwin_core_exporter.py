"""Darwin Core Archive exporter for detection data.

Generates standardized DwC-A ZIP files containing:
  - occurrence.csv (core records)
  - meta.xml (archive descriptor)
  - eml.xml (dataset metadata in EML 2.1.1 format)
"""

import csv
import io
import json
import shutil
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional
from xml.dom import minidom


def _prettify_xml(element: ET.Element) -> str:
    rough = ET.tostring(element, encoding="unicode")
    return (
        minidom.parseString(rough)
        .toprettyxml(indent="  ", encoding="UTF-8")
        .decode("utf-8")
    )


DWC_TERMS = {
    "occurrenceID": "http://rs.tdwg.org/dwc/terms/occurrenceID",
    "basisOfRecord": "http://rs.tdwg.org/dwc/terms/basisOfRecord",
    "scientificName": "http://rs.tdwg.org/dwc/terms/scientificName",
    "vernacularName": "http://rs.tdwg.org/dwc/terms/vernacularName",
    "eventDate": "http://rs.tdwg.org/dwc/terms/eventDate",
    "locality": "http://rs.tdwg.org/dwc/terms/locality",
    "decimalLatitude": "http://rs.tdwg.org/dwc/terms/decimalLatitude",
    "decimalLongitude": "http://rs.tdwg.org/dwc/terms/decimalLongitude",
    "geodeticDatum": "http://rs.tdwg.org/dwc/terms/geodeticDatum",
    "coordinateUncertaintyInMeters": "http://rs.tdwg.org/dwc/terms/coordinateUncertaintyInMeters",
    "occurrenceStatus": "http://rs.tdwg.org/dwc/terms/occurrenceStatus",
    "identificationVerificationStatus": "http://rs.tdwg.org/dwc/terms/identificationVerificationStatus",
    "institutionCode": "http://rs.tdwg.org/dwc/terms/institutionCode",
    "datasetName": "http://rs.tdwg.org/dwc/terms/datasetName",
    "samplingProtocol": "http://rs.tdwg.org/dwc/terms/samplingProtocol",
    "kingdom": "http://rs.tdwg.org/dwc/terms/kingdom",
    "phylum": "http://rs.tdwg.org/dwc/terms/phylum",
    "class": "http://rs.tdwg.org/dwc/terms/class",
}

OCCURRENCE_COLUMNS = [
    "occurrenceID",
    "basisOfRecord",
    "kingdom",
    "phylum",
    "class",
    "scientificName",
    "vernacularName",
    "eventDate",
    "locality",
    "decimalLatitude",
    "decimalLongitude",
    "geodeticDatum",
    "coordinateUncertaintyInMeters",
    "occurrenceStatus",
    "identificationVerificationStatus",
    "institutionCode",
    "datasetName",
    "samplingProtocol",
]


class DarwinCoreExporter:
    def __init__(self, detection_store=None):
        self.store = detection_store

    def export_archive(
        self,
        detections: list,
        metadata: dict,
        output_dir: Optional[Path] = None,
    ) -> Path:
        work_dir = Path(output_dir or tempfile.mkdtemp(prefix="dwca_"))
        work_dir.mkdir(parents=True, exist_ok=True)

        self._write_occurrences(detections, metadata, work_dir)
        self._write_meta_xml(work_dir)
        self._write_eml(detections, metadata, work_dir)

        zip_stem = work_dir / "dwca_export"
        zip_path = shutil.make_archive(str(zip_stem), "zip", work_dir)
        return Path(zip_path)

    def _detection_to_occurrence(self, det: dict, metadata: dict) -> dict:
        verification = det.get("verification", "unverified")
        return {
            "occurrenceID": det.get("detection_id", ""),
            "basisOfRecord": "MachineObservation",
            "kingdom": "Animalia",
            "phylum": "Chordata",
            "class": "Aves",
            "scientificName": det.get("species_scientific") or det.get("species", ""),
            "vernacularName": det.get("species_chinese", ""),
            "eventDate": det.get("detected_at", ""),
            "locality": det.get("site_name", ""),
            "decimalLatitude": det.get("latitude", ""),
            "decimalLongitude": det.get("longitude", ""),
            "geodeticDatum": "WGS84",
            "coordinateUncertaintyInMeters": 100,
            "occurrenceStatus": "present",
            "identificationVerificationStatus": verification,
            "institutionCode": metadata.get("institution", ""),
            "datasetName": metadata.get(
                "dataset_name", "Biodiversity Survey Platform Detections"
            ),
            "samplingProtocol": "passive acoustic monitoring; CNN classification",
        }

    def _write_occurrences(self, detections: list, metadata: dict, out_dir: Path):
        path = out_dir / "occurrence.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=OCCURRENCE_COLUMNS, extrasaction="ignore"
            )
            writer.writeheader()
            for det in detections:
                row = self._detection_to_occurrence(det, metadata)
                writer.writerow(row)

    def _write_meta_xml(self, out_dir: Path):
        archive = ET.Element("archive")
        archive.set("xmlns", "http://rs.tdwg.org/dwc/text/")
        archive.set("metadata", "eml.xml")

        core = ET.SubElement(archive, "core")
        core.set("encoding", "UTF-8")
        core.set("fieldsTerminatedBy", ",")
        core.set("linesTerminatedBy", "\\n")
        core.set("fieldsEnclosedBy", '"')
        core.set("ignoreHeaderLines", "1")
        core.set("rowType", "http://rs.tdwg.org/dwc/terms/Occurrence")

        files = ET.SubElement(core, "files")
        ET.SubElement(files, "location").text = "occurrence.csv"

        ET.SubElement(core, "id").set("index", "0")

        for i, col in enumerate(OCCURRENCE_COLUMNS):
            if i == 0:
                continue
            if col in DWC_TERMS:
                field = ET.SubElement(core, "field")
                field.set("index", str(i))
                field.set("term", DWC_TERMS[col])

        (out_dir / "meta.xml").write_text(_prettify_xml(archive), encoding="utf-8")

    def _write_eml(self, detections: list, metadata: dict, out_dir: Path):
        dates = [d.get("detected_at", "") for d in detections if d.get("detected_at")]
        start_date = min(dates) if dates else ""
        end_date = max(dates) if dates else ""

        lats = [
            float(d["latitude"]) for d in detections if d.get("latitude") is not None
        ]
        lons = [
            float(d["longitude"]) for d in detections if d.get("longitude") is not None
        ]

        eml_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<eml:eml xmlns:eml="eml://ecoinformatics.org/eml-2.1.1"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="eml://ecoinformatics.org/eml-2.1.1 eml.xsd"
         packageId="biodiversity-survey-platform-export" system="http://gbif.org" scope="system">
  <dataset>
    <title>{metadata.get("dataset_name", "Biodiversity Survey Platform Acoustic Detections")}</title>
    <creator>
      <organizationName>{metadata.get("institution", "Biodiversity Survey Platform")}</organizationName>
    </creator>
    <metadataProvider>
      <organizationName>{metadata.get("institution", "Biodiversity Survey Platform")}</organizationName>
    </metadataProvider>
    <language>en</language>
    <abstract>
      <para>Automated acoustic detections exported from the Biodiversity Survey Platform.
Contains {len(detections)} occurrence records generated via CNN-based species classification
with passive acoustic monitoring.</para>
    </abstract>
    <coverage>
      <geographicCoverage>
        <geographicDescription>{metadata.get("geographic_description", "Study area")}</geographicDescription>
        <boundingCoordinates>
          <westBoundingCoordinate>{min(lons) if lons else metadata.get("min_lon", 100)}</westBoundingCoordinate>
          <eastBoundingCoordinate>{max(lons) if lons else metadata.get("max_lon", 122)}</eastBoundingCoordinate>
          <northBoundingCoordinate>{max(lats) if lats else metadata.get("max_lat", 32)}</northBoundingCoordinate>
          <southBoundingCoordinate>{min(lats) if lats else metadata.get("min_lat", 18)}</southBoundingCoordinate>
        </boundingCoordinates>
      </geographicCoverage>
      <temporalCoverage>
        <rangeOfDates>
          <beginDate><calendarDate>{start_date[:10] if start_date else ""}</calendarDate></beginDate>
          <endDate><calendarDate>{end_date[:10] if end_date else ""}</calendarDate></endDate>
        </rangeOfDates>
      </temporalCoverage>
      <taxonomicCoverage>
        <generalTaxonomicCoverage>Bird species detected via passive acoustic monitoring</generalTaxonomicCoverage>
        <taxonomicClassification>
          <taxonRankName>Class</taxonRankName>
          <taxonRankValue>Aves</taxonRankValue>
        </taxonomicClassification>
      </taxonomicCoverage>
    </coverage>
    <methods>
      <methodStep>
        <description>
          <para>Passive acoustic monitoring using autonomous recording units (ARUs).
Audio recordings analyzed with CNN-based bird species classifier.
Detections above confidence threshold included in dataset.</para>
        </description>
      </methodStep>
    </methods>
  </dataset>
</eml:eml>"""
        (out_dir / "eml.xml").write_text(eml_xml, encoding="utf-8")

    def get_filtered_detections(
        self,
        species_filter: list = None,
        date_start: str = None,
        date_end: str = None,
        min_confidence: float = 0.0,
        verified_only: bool = False,
    ) -> list:
        if not self.store:
            return []
        all_dets = self.store.get_all_detections()
        filtered = []
        for det in all_dets:
            if species_filter:
                sp = det.get("species_scientific") or det.get("species", "")
                if sp not in species_filter:
                    continue
            if date_start and det.get("detected_at", "") < date_start:
                continue
            if date_end and det.get("detected_at", "") > date_end:
                continue
            conf = det.get("confidence", 0)
            if isinstance(conf, (int, float)) and conf < min_confidence:
                continue
            if verified_only and det.get("verification") != "confirmed":
                continue
            filtered.append(det)
        return filtered
