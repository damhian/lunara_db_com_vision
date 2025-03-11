from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, JSON, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import uuid

Base = declarative_base()

class MsCCTV(Base):
    __tablename__ = "ms_cctv"
    Id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    CCTV_Name = Column(String(255), nullable=False)
    Ruas_Name = Column(String(255))
    Stream_url = Column(Text, nullable=False)
    Lat = Column(Float)
    Long = Column(Float)
    BUJT = Column(String(100))
    BUJT_NAME = Column(String(255))
    Created_at = Column(DateTime, default=func.now())
    Updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    rois = relationship("MsROI", back_populates="cctv")
    
    def to_dict(self):
        return {
            "id": str(self.Id),
            "cctv_name": self.CCTV_Name,
            "ruas_name": self.Ruas_Name,
            "stream_url": self.Stream_url,
            "latitude": self.Lat,
            "longitude": self.Long,
            "bujt": self.BUJT,
            "bujt_name": self.BUJT_NAME,
            "created_at": self.Created_at,
            "updated_at": self.Updated_at,
        }

class MsROI(Base):
    __tablename__ = "ms_roi"
    
    Id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    Id_CCTV = Column(UUID(as_uuid=True), ForeignKey("ms_cctv.Id", ondelete="CASCADE"), nullable=False)
    CCTV_Name = Column(String, nullable=False)
    Label = Column(String, nullable=False)
    ROI = Column(JSON, nullable=False)
    Created_at = Column(DateTime, nullable=False, default=func.now())
    Updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    # Relationships
    cctv = relationship("MsCCTV", back_populates="rois")
    counted_vhc = relationship("CountedVhcPerROI", back_populates="roi", cascade="all, delete-orphan")
    avg_speeds = relationship("EstAvgSpeedPerROI", back_populates="roi", cascade="all, delete-orphan")
    dwelling_times = relationship("AvgVHCDwellingTimePerROI", back_populates="roi", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": str(self.Id),
            "id_cctv": str(self.Id_CCTV),
            "cctv_name": self.CCTV_Name,
            "label": self.Label,
            "roi": self.ROI,
            "created_at": self.Created_at,
            "updated_at": self.Updated_at,
        }

class CountedVhcPerROI(Base):
    __tablename__ = "counted_vhc_per_roi"
    Id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    CCTV_Name = Column(String(255), nullable=False)
    Id_CCTV = Column(UUID(as_uuid=True), ForeignKey("ms_cctv.Id", ondelete="CASCADE"), nullable=False)
    Id_ROI = Column(UUID(as_uuid=True), ForeignKey("ms_roi.Id", ondelete="CASCADE"), nullable=False)
    ROI_Label = Column(String(100), nullable=False)
    VHC_Type = Column(String(50), nullable=False)
    Num_of_VHC = Column(Integer, default=0)
    Created_at = Column(DateTime, default=func.now())
    Updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    roi = relationship("MsROI", back_populates="counted_vhc")

class EstAvgSpeedPerROI(Base):
    __tablename__ = "est_avg_speed_per_roi"
    Id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    Id_CCTV = Column(UUID(as_uuid=True), ForeignKey("ms_cctv.Id", ondelete="CASCADE"), nullable=False)
    CCTV_Name = Column(String(255), nullable=False)
    Id_ROI = Column(UUID(as_uuid=True), ForeignKey("ms_roi.Id", ondelete="CASCADE"), nullable=False)
    ROI_Label = Column(String(100), nullable=False)
    Vhc_Type = Column(String(50), nullable=False)
    Vhc_Avg_Speed_Est = Column(Float, nullable=False)
    Created_at = Column(DateTime, default=func.now())
    Updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    roi = relationship("MsROI", back_populates="avg_speeds")

class AvgVHCDwellingTimePerROI(Base):
    __tablename__ = "avg_vhc_dwelling_time_per_roi"
    Id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    Id_CCTV = Column(UUID(as_uuid=True), ForeignKey("ms_cctv.Id", ondelete="CASCADE"), nullable=False)
    CCTV_Name = Column(String(255), nullable=False)
    Id_ROI = Column(UUID(as_uuid=True), ForeignKey("ms_roi.Id", ondelete="CASCADE"), nullable=False)
    ROI_Label = Column(String(100), nullable=False)
    Vhc_Type = Column(String(50), nullable=False)
    Vhc_Dwelling_time = Column(Float, nullable=False)
    Created_at = Column(DateTime, default=func.now())
    Updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    roi = relationship("MsROI", back_populates="dwelling_times")

# print(Base.metadata.tables)
