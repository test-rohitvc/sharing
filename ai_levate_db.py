from typing import List, Dict, Any
from sqlalchemy import ForeignKey, String, UniqueConstraint, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

# optimize JSON storage for PostgreSQL while maintaining compatibility with SQLite
OptimizedJSON = JSON().with_variant(JSONB, "postgresql")

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String, nullable=False)
    mfa_question: Mapped[str] = mapped_column(String, nullable=False)
    mfa_answer: Mapped[str] = mapped_column(String, nullable=False)

    # A user can have multiple solutions
    solutions: Mapped[List["Solution"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

class Solution(Base):
    __tablename__ = "solutions"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    icon: Mapped[str] = mapped_column(String(10), nullable=False) # Emoji
    sol_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    framework: Mapped[str] = mapped_column(String, nullable=False)
    
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Navigating back to the exact User who owns this solution
    user: Mapped["User"] = relationship(back_populates="solutions")

    # A solution can have multiple capabilities and data planes
    capabilities: Mapped[List["Capability"]] = relationship(
        back_populates="solution", cascade="all, delete-orphan"
    )
    data_planes: Mapped[List["DataPlane"]] = relationship(
        back_populates="solution", cascade="all, delete-orphan"
    )


class Capability(Base):
    __tablename__ = "capabilities"

    id: Mapped[str] = mapped_column(primary_key=True)
    capability_type: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[Dict[str, Any]] = mapped_column(OptimizedJSON, default=dict, nullable=False)
    

    sol_id: Mapped[str] = mapped_column(ForeignKey("solutions.id"), nullable=False)

    # Navigating back to the exact Solution this capability belongs to
    solution: Mapped["Solution"] = relationship(back_populates="capabilities")

    # Enforces that a specific solution can only have ONE of each capability_type
    __table_args__ = (
        UniqueConstraint("sol_id", "capability_type", name="uq_solution_capability"),
    )

class DataPlane(Base):
    __tablename__ = "data_planes"

    id: Mapped[str] = mapped_column(primary_key=True)
    plane_type: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[Dict[str, Any]] = mapped_column(OptimizedJSON, default=dict, nullable=False)
    
    sol_id: Mapped[str] = mapped_column(ForeignKey("solutions.id"), nullable=False)

    # Navigating back to the exact Solution this data plane belongs to
    solution: Mapped["Solution"] = relationship(back_populates="data_planes")

    # Enforces that a specific solution can only have ONE of each plane_type
    __table_args__ = (
        UniqueConstraint("sol_id", "plane_type", name="uq_solution_dataplane"),
    )
