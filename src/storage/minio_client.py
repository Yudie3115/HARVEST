"""
MinIO object storage client
"""
from pathlib import Path
from typing import Optional
from uuid import uuid4
from minio import Minio
from minio.error import S3Error
from loguru import logger

from src.config.settings import settings


class MinIOClient:
    """MinIO object storage client"""
    
    def __init__(
        self,
        endpoint: str = None,
        access_key: str = None,
        secret_key: str = None,
        bucket: str = None,
        secure: bool = None
    ):
        self.endpoint = endpoint or settings.minio_endpoint
        self.access_key = access_key or settings.minio_access_key
        self.secret_key = secret_key or settings.minio_secret_key
        self.bucket = bucket or settings.minio_bucket
        self.secure = secure if secure is not None else settings.minio_secure
        
        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure
        )
        
        logger.info(f"Initialized MinIO client: {self.endpoint}")
        self.ensure_bucket()
    
    def ensure_bucket(self):
        """Ensure bucket exists, create if not"""
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
                logger.info(f"Created bucket: {self.bucket}")
            else:
                logger.debug(f"Bucket exists: {self.bucket}")
        except S3Error as e:
            logger.error(f"Error ensuring bucket: {e}")
            raise
    
    def upload_file(
        self,
        file_path: str,
        object_name: str = None,
        content_type: str = "application/octet-stream"
    ) -> str:
        """
        Upload a file to MinIO
        
        Args:
            file_path: Path to local file
            object_name: Name in bucket (auto-generated if None)
            content_type: MIME type
            
        Returns:
            Object path in MinIO
        """
        if object_name is None:
            # Generate unique name
            suffix = Path(file_path).suffix
            object_name = f"{uuid4()}{suffix}"
        
        try:
            self.client.fput_object(
                self.bucket,
                object_name,
                file_path,
                content_type=content_type
            )
            logger.debug(f"Uploaded {file_path} to {object_name}")
            return object_name
        except S3Error as e:
            logger.error(f"Error uploading file: {e}")
            raise
    
    def upload_bytes(
        self,
        data: bytes,
        object_name: str = None,
        content_type: str = "application/octet-stream"
    ) -> str:
        """
        Upload bytes to MinIO
        
        Args:
            data: Bytes to upload
            object_name: Name in bucket (auto-generated if None)
            content_type: MIME type
            
        Returns:
            Object path in MinIO
        """
        import io
        
        if object_name is None:
            object_name = str(uuid4())
        
        try:
            self.client.put_object(
                self.bucket,
                object_name,
                io.BytesIO(data),
                length=len(data),
                content_type=content_type
            )
            logger.debug(f"Uploaded {len(data)} bytes to {object_name}")
            return object_name
        except S3Error as e:
            logger.error(f"Error uploading bytes: {e}")
            raise
    
    def upload_stream(
        self,
        stream,
        length: int,
        object_name: str,
        content_type: str = "application/octet-stream"
    ) -> str:
        """
        Upload from a file-like object without reading it into memory.

        Used for Admin uploads, where holding the whole file in the web
        process is what made concurrent uploads exhaust the container.

        Args:
            stream:       File-like object positioned at the start
            length:       Total size in bytes (must be known)
            object_name:  Name in bucket
            content_type: MIME type

        Returns:
            Object path in MinIO
        """
        try:
            self.client.put_object(
                self.bucket,
                object_name,
                stream,
                length=length,
                content_type=content_type
            )
            logger.debug(f"Streamed {length} bytes to {object_name}")
            return object_name
        except S3Error as e:
            logger.error(f"Error streaming upload: {e}")
            raise

    def download_file(self, object_name: str, file_path: str):
        """
        Download a file from MinIO
        
        Args:
            object_name: Name in bucket
            file_path: Local path to save
        """
        try:
            self.client.fget_object(self.bucket, object_name, file_path)
            logger.debug(f"Downloaded {object_name} to {file_path}")
        except S3Error as e:
            logger.error(f"Error downloading file: {e}")
            raise
    
    def get_object(self, object_name: str) -> bytes:
        """
        Get object data as bytes
        
        Args:
            object_name: Name in bucket
            
        Returns:
            Object data as bytes
        """
        try:
            response = self.client.get_object(self.bucket, object_name)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as e:
            logger.error(f"Error getting object: {e}")
            raise
    
    def delete_object(self, object_name: str):
        """Delete an object from MinIO"""
        try:
            self.client.remove_object(self.bucket, object_name)
            logger.debug(f"Deleted {object_name}")
        except S3Error as e:
            logger.error(f"Error deleting object: {e}")
            raise
    
    def list_objects(self, prefix: str = None) -> list:
        """List objects in bucket"""
        try:
            objects = self.client.list_objects(
                self.bucket,
                prefix=prefix,
                recursive=True
            )
            return [obj.object_name for obj in objects]
        except S3Error as e:
            logger.error(f"Error listing objects: {e}")
            raise
    
    def get_presigned_url(self, object_name: str, expires_seconds: int = 3600) -> str:
        """
        Get a presigned URL for object access
        
        Args:
            object_name: Name in bucket
            expires_seconds: URL expiration time
            
        Returns:
            Presigned URL
        """
        try:
            from datetime import timedelta
            url = self.client.presigned_get_object(
                self.bucket,
                object_name,
                expires=timedelta(seconds=expires_seconds)
            )
            return url
        except S3Error as e:
            logger.error(f"Error generating presigned URL: {e}")
            raise
