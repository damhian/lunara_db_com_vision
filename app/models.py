from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, JSON, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import uuid

Base = declarative_base()

class MsCCTV(Base):
    __tablename__ = "ms_cctv"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nama_lokasi = Column(String(255), nullable=False)
    nama_cctv = Column(String(255), nullable=False)
    stream_url = Column(Text)
    status = Column(String(50), nullable=False, default="offline")
    nama_pengelola = Column(String(255))
    protocol = Column(String(50), nullable=False, default="embedded")
    latitude = Column(Float)
    longitude = Column(Float)
    source = Column(String(50), nullable=False, default="stasiun")
    tag_kategori = Column(String(50), nullable=False, default="stasiun")
    matra = Column(String(50), nullable=False, default="ka")
    nama_kabupaten_kota = Column(String(255))
    nama_provinsi = Column(String(255))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    rois = relationship("MsROI", back_populates="cctv")
    
    def to_dict(self):
        return {
             "id": str(self.id),
            "nama_lokasi": self.nama_lokasi,
            "nama_cctv": self.nama_cctv,
            "stream_url": self.stream_url,
            "status": self.status,
            "nama_pengelola": self.nama_pengelola,
            "protocol": self.protocol,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "source": self.source,
            "tag_kategori": self.tag_kategori,
            "matra": self.matra,
            "nama_kabupaten_kota": self.nama_kabupaten_kota,
            "nama_provinsi": self.nama_provinsi,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

class MsROI(Base):
    __tablename__ = "ms_roi"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_cctv = Column(UUID(as_uuid=True), ForeignKey("ms_cctv.id", ondelete="CASCADE"), nullable=False)
    nama_cctv = Column(String, nullable=False)
    label = Column(String, nullable=False)
    roi = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    # Relationships
    cctv = relationship("MsCCTV", back_populates="rois")
    counted_vhc = relationship("CountedVhcPerROI", back_populates="roi", cascade="all, delete-orphan")
    avg_speeds = relationship("EstAvgSpeedPerROI", back_populates="roi", cascade="all, delete-orphan")
    dwelling_times = relationship("AvgVHCDwellingTimePerROI", back_populates="roi", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": str(self.id),
            "id_cctv": str(self.id_cctv),
            "nama_cctv": self.nama_cctv,
            "label": self.label,
            "roi": self.roi,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

class CountedVhcPerROI(Base):
    __tablename__ = "counted_vhc_per_roi"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nama_cctv = Column(String(255), nullable=False)
    id_cctv = Column(UUID(as_uuid=True), ForeignKey("ms_cctv.id", ondelete="CASCADE"), nullable=False)
    id_roi = Column(UUID(as_uuid=True), ForeignKey("ms_roi.id", ondelete="CASCADE"), nullable=False)
    roi_label = Column(String(100), nullable=False)
    tipe_vhc = Column(String(50), nullable=False)
    jml_vhc = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    roi = relationship("MsROI", back_populates="counted_vhc")

class EstAvgSpeedPerROI(Base):
    __tablename__ = "est_avg_speed_per_roi"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_cctv = Column(UUID(as_uuid=True), ForeignKey("ms_cctv.id", ondelete="CASCADE"), nullable=False)
    nama_cctv = Column(String(255), nullable=False)
    id_roi = Column(UUID(as_uuid=True), ForeignKey("ms_roi.id", ondelete="CASCADE"), nullable=False)
    roi_label = Column(String(100), nullable=False)
    tipe_vhc = Column(String(50), nullable=False)
    rata_rata_kecepatan = Column(Float, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    roi = relationship("MsROI", back_populates="avg_speeds")

class AvgVHCDwellingTimePerROI(Base):
    __tablename__ = "avg_vhc_dwelling_time_per_roi"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_cctv = Column(UUID(as_uuid=True), ForeignKey("ms_cctv.id", ondelete="CASCADE"), nullable=False)
    nama_cctv = Column(String(255), nullable=False)
    id_roi = Column(UUID(as_uuid=True), ForeignKey("ms_roi.id", ondelete="CASCADE"), nullable=False)
    roi_label = Column(String(100), nullable=False)
    tipe_vhc = Column(String(50), nullable=False)
    waktu_tunggu_rata_rata = Column(Float, nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    roi = relationship("MsROI", back_populates="dwelling_times")

# print(Base.metadata.tables)
