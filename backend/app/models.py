"""Relational storage for the tracker. JSON columns hold compatibility metadata only."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey,
    ForeignKeyConstraint, Index, Integer, JSON, MetaData, Numeric, String,
    Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql.functions import FunctionElement


NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
JSON_VALUE = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")


class Trimmed(FunctionElement):
    """Use PostgreSQL's canonical function spelling for stable index reflection."""
    type = Text()
    inherit_cache = True


@compiles(Trimmed)
def _trimmed_default(element, compiler, **kwargs):
    return "trim(" + compiler.process(element.clauses, **kwargs) + ")"


@compiles(Trimmed, "postgresql")
def _trimmed_postgresql(element, compiler, **kwargs):
    return "btrim(" + compiler.process(element.clauses, **kwargs) + ")"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class MasterMetadata:
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class BusinessEntity(MasterMetadata, Base):
    __tablename__ = "business_entity"
    business_entity_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    __table_args__ = (
        CheckConstraint("length(trim(business_entity_id)) > 0", name="id_not_blank"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        Index("uq_business_entity_name_ci", func.lower(Trimmed(name)), unique=True),
    )


class FundingSource(MasterMetadata, Base):
    __tablename__ = "funding_source"
    funding_source_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    __table_args__ = (
        CheckConstraint("length(trim(funding_source_id)) > 0", name="id_not_blank"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        Index("uq_funding_source_name_ci", func.lower(Trimmed(name)), unique=True),
    )


class ProjectFamily(MasterMetadata, Base):
    __tablename__ = "project_family"
    project_family_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    business_entity_id: Mapped[str] = mapped_column(
        Text, ForeignKey("business_entity.business_entity_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    funding_source_id: Mapped[str] = mapped_column(
        Text, ForeignKey("funding_source.funding_source_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    __table_args__ = (
        CheckConstraint("length(trim(project_family_id)) > 0", name="id_not_blank"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        Index("uq_project_family_name_ci", func.lower(Trimmed(name)), unique=True),
    )


class Project(MasterMetadata, Base):
    __tablename__ = "project"
    project_id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_name: Mapped[str] = mapped_column(Text, nullable=False)
    project_key: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    project_family_id: Mapped[str] = mapped_column(
        Text, ForeignKey("project_family.project_family_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    engineering_project_manager: Mapped[str] = mapped_column(Text, nullable=False)
    supply_chain_program_manager: Mapped[str] = mapped_column(Text, nullable=False, default="")
    platform: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prototype: Mapped[Optional[bool]] = mapped_column(Boolean)
    parent_project_id: Mapped[Optional[str]] = mapped_column(Text, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    __table_args__ = (
        ForeignKeyConstraint(["parent_project_id"], ["project.project_id"],
                             deferrable=True, initially="DEFERRED", ondelete="NO ACTION"),
        CheckConstraint("length(trim(project_id)) > 0", name="id_not_blank"),
        CheckConstraint("length(trim(project_name)) > 0", name="name_not_blank"),
        CheckConstraint("length(trim(engineering_project_manager)) > 0", name="epm_not_blank"),
        CheckConstraint("project_key IS NULL OR length(trim(project_key)) > 0", name="key_not_blank"),
        CheckConstraint("parent_project_id IS NULL OR parent_project_id <> project_id", name="not_own_parent"),
        Index("uq_project_name_ci", func.lower(Trimmed(project_name)), unique=True),
    )


class ASIC(MasterMetadata, Base):
    __tablename__ = "asic"
    asic_id: Mapped[str] = mapped_column(Text, primary_key=True)
    asic_name: Mapped[str] = mapped_column(Text, nullable=False)
    si_ops_supply_chain_project_manager: Mapped[str] = mapped_column(Text, nullable=False)
    marketing_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    historical_price_unknown: Mapped[Optional[bool]] = mapped_column(Boolean)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    __table_args__ = (
        CheckConstraint("length(trim(asic_id)) > 0", name="id_not_blank"),
        CheckConstraint("length(trim(asic_name)) > 0", name="name_not_blank"),
        CheckConstraint("length(trim(si_ops_supply_chain_project_manager)) > 0", name="owner_not_blank"),
        CheckConstraint("unit_price >= 0 AND unit_price <> 'NaN'", name="price_nonnegative_finite"),
        Index("uq_asic_name_ci", func.lower(Trimmed(asic_name)), unique=True),
    )


class ASICPart(Base):
    __tablename__ = "asic_mpn"
    part_id: Mapped[str] = mapped_column(Text, primary_key=True)
    asic_id: Mapped[str] = mapped_column(Text, ForeignKey("asic.asic_id", ondelete="RESTRICT"), nullable=False)
    mpn: Mapped[str] = mapped_column(Text, nullable=False)
    customer_part_number: Mapped[str] = mapped_column(Text, nullable=False, default="")
    plid: Mapped[str] = mapped_column(Text, nullable=False, default="")
    component_assembly_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    component_sub_type: Mapped[str] = mapped_column(Text, nullable=False, default="")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    __table_args__ = (
        CheckConstraint("length(trim(part_id)) > 0", name="id_not_blank"),
        CheckConstraint("length(trim(mpn)) > 0", name="mpn_not_blank"),
        Index("uq_asic_mpn_per_asic_ci", asic_id, func.lower(Trimmed(mpn)), unique=True),
    )


class ASICPriceHistory(Base):
    __tablename__ = "asic_price_history"
    asic_id: Mapped[str] = mapped_column(Text, ForeignKey("asic.asic_id", ondelete="RESTRICT"), primary_key=True)
    effective_quarter: Mapped[str] = mapped_column(String(7), primary_key=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    __table_args__ = (
        CheckConstraint("unit_price >= 0 AND unit_price <> 'NaN'", name="price_nonnegative_finite"),
        CheckConstraint("length(effective_quarter) = 7 AND substr(effective_quarter, 5, 2) = '-Q' "
                        "AND substr(effective_quarter, 7, 1) IN ('1','2','3','4')", name="quarter_shape"),
    )


class ProjectASIC(Base):
    __tablename__ = "project_asic"
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("project.project_id", ondelete="RESTRICT"), primary_key=True)
    asic_id: Mapped[str] = mapped_column(Text, ForeignKey("asic.asic_id", ondelete="RESTRICT"), primary_key=True, index=True)
    shipping_time_days: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    __table_args__ = (CheckConstraint("shipping_time_days >= 0", name="transit_nonnegative"),)


class PlanningEvent(Base):
    __tablename__ = "planning_event"
    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    asic_id: Mapped[str] = mapped_column(Text, ForeignKey("asic.asic_id", ondelete="RESTRICT"), nullable=False, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(Text, ForeignKey("project.project_id", ondelete="RESTRICT"), index=True)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ship_days: Mapped[Optional[int]] = mapped_column(Integer)
    requested_ship_date: Mapped[Optional[date]] = mapped_column(Date)
    available_ship_date: Mapped[Optional[date]] = mapped_column(Date)
    eta: Mapped[Optional[date]] = mapped_column(Date)
    request_reference: Mapped[Optional[str]] = mapped_column(Text, index=True)
    canonical_request_id: Mapped[Optional[str]] = mapped_column(Text, index=True)
    # Raw ISO values retain date-only legacy creation semantics used by FIFO.
    created_at_text: Mapped[Optional[str]] = mapped_column(Text)
    updated_at_text: Mapped[Optional[str]] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    __table_args__ = (
        ForeignKeyConstraint(["canonical_request_id"], ["planning_event.event_id"],
                             deferrable=True, initially="DEFERRED", ondelete="NO ACTION"),
        CheckConstraint("event_type IN ('expected_ship','request','expected_fulfilment','actual_ship','actual_fulfilment')", name="type_valid"),
        CheckConstraint("quantity > 0 AND quantity <= 9007199254740991", name="quantity_positive_safe"),
        CheckConstraint("ship_days IS NULL OR ship_days >= 0", name="transit_nonnegative"),
        CheckConstraint("(event_type = 'expected_ship' AND project_id IS NULL) OR "
                        "(event_type <> 'expected_ship' AND project_id IS NOT NULL)", name="project_scope"),
        CheckConstraint("event_type <> 'request' OR requested_ship_date IS NULL OR requested_ship_date <= event_date", name="request_ship_before_arrival"),
        CheckConstraint("event_type <> 'expected_fulfilment' OR available_ship_date IS NULL OR available_ship_date <= event_date", name="allocation_ship_before_arrival"),
        CheckConstraint("event_type <> 'actual_ship' OR (eta IS NOT NULL AND eta >= event_date)", name="shipment_eta_valid"),
    )


class ForecastVersion(Base):
    __tablename__ = "forecast_version"
    forecast_version_id: Mapped[str] = mapped_column(Text, primary_key=True)
    version_month: Mapped[str] = mapped_column(String(7), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_text: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    __table_args__ = (CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),)


class ForecastLine(Base):
    __tablename__ = "forecast_line"
    forecast_version_id: Mapped[str] = mapped_column(
        Text, ForeignKey("forecast_version.forecast_version_id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Frozen snapshot IDs and labels intentionally do not reference mutable masters.
    asic_id: Mapped[str] = mapped_column(Text, nullable=False)
    asic_name: Mapped[str] = mapped_column(Text, nullable=False)
    project_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    project_name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    phase: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    period_month: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_event_id: Mapped[Optional[str]] = mapped_column(Text)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    __table_args__ = (
        CheckConstraint("quantity >= 0 AND quantity <= 9007199254740991", name="quantity_nonnegative_safe"),
        CheckConstraint("event_type IN ('expected_ship','request','expected_fulfilment','actual_ship','actual_fulfilment')", name="type_valid"),
    )


class RecoverySnapshot(Base):
    __tablename__ = "recovery_snapshot"
    snapshot_id: Mapped[str] = mapped_column(Text, primary_key=True)
    captured_at_text: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class WorkspaceMeta(Base):
    __tablename__ = "workspace_meta"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint("revision >= 0", name="revision_nonnegative"),
    )


class AuditEntry(Base):
    __tablename__ = "audit_entry"
    audit_id: Mapped[str] = mapped_column(Text, primary_key=True)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    workspace_revision: Mapped[Optional[int]] = mapped_column(BigInteger, index=True)
    occurred_at_text: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    action: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    actor_subject: Mapped[Optional[str]] = mapped_column(Text, index=True)
    actor_display_name: Mapped[Optional[str]] = mapped_column(Text)
    actor_role: Mapped[Optional[str]] = mapped_column(String(32))
    is_legacy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
