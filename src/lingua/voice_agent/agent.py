"""LiveKit voice agent session management."""
import os
import asyncio
from typing import AsyncGenerator
from contextlib import asynccontextmanager

from src.lingua.core.config import VoiceAgentConfig


class VoiceSession:
    """Manages LiveKit WebSocket lifecycle for voice tutoring sessions.

    This class provides a high-level interface for connecting to LiveKit,
    streaming audio, and receiving transcription/translation responses.

    Args:
        config: VoiceAgentConfig containing session parameters

    Raises:
        ImportError: If livekit package is not installed
    """

    def __init__(self, config: VoiceAgentConfig) -> None:
        """Initialize the voice session with configuration.

        Args:
            config: VoiceAgentConfig containing session parameters
        """
        self.config = config
        self._connected = False
        self._room = None

        # Check if livekit is available
        try:
            import livekit  # noqa: F401
            self._livekit_available = True
        except ImportError:
            self._livekit_available = False

    @property
    def is_configured(self) -> bool:
        """Check if LiveKit environment variables are configured.

        Returns:
            True if LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET are set
        """
        return bool(
            os.getenv("LIVEKIT_URL")
            and os.getenv("LIVEKIT_API_KEY")
            and os.getenv("LIVEKIT_API_SECRET")
        )

    def is_connected(self) -> bool:
        """Check if currently connected to LiveKit.

        Returns:
            True if connected, False otherwise
        """
        return self._connected

    async def connect(self) -> None:
        """Connect to LiveKit using environment variables.

        Raises:
            ImportError: If livekit package is not installed
            RuntimeError: If LiveKit is not configured (missing env vars)
        """
        if not self._livekit_available:
            raise ImportError(
                "livekit package not installed. Install with: pip install livekit"
            )

        if not self.is_configured:
            raise RuntimeError(
                "LiveKit not configured. Set LIVEKIT_URL, LIVEKIT_API_KEY, "
                "and LIVEKIT_API_SECRET environment variables."
            )

        # Import here after confirming availability
        from livekit import LiveKit

        # Get configuration from environment
        livekit_url = os.getenv("LIVEKIT_URL")
        api_key = os.getenv("LIVEKIT_API_KEY")
        api_secret = os.getenv("LIVEKIT_API_SECRET")

        # Connect to LiveKit room
        # The room name can be customized; using a default for tutoring
        room_name = f"lingua_tutor_{self.config.language}"

        try:
            # Create LiveKit connection
            self._room = await LiveKit.connect(
                url=livekit_url,
                api_key=api_key,
                api_secret=api_secret,
                room=room_name,
            )
            self._connected = True
        except Exception as e:
            self._connected = False
            raise RuntimeError(f"Failed to connect to LiveKit: {e}") from e

    async def disconnect(self) -> None:
        """Close the LiveKit connection gracefully."""
        if self._room is not None:
            try:
                await self._room.disconnect()
            except Exception:
                pass  # Best effort disconnect
            finally:
                self._room = None
        self._connected = False

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Stream audio bytes to LiveKit.

        Args:
            audio_bytes: Raw audio data to send

        Raises:
            RuntimeError: If not connected to LiveKit
        """
        if not self._connected or self._room is None:
            raise RuntimeError("Not connected to LiveKit. Call connect() first.")

        # Send audio to the room
        # In a real implementation, this would publish to a data track
        # For now, this is a placeholder that logs the audio size
        # Actual implementation depends on specific LiveKit use case
        _ = audio_bytes  # Placeholder for actual implementation
        # await self._room.publish_data(audio_bytes, kind=DataKind.AUDIO)

    async def stream_response(self) -> AsyncGenerator[str, None]:
        """Stream transcription/translation response back from the agent.

        Yields:
            Text chunks from the agent response

        Raises:
            RuntimeError: If not connected to LiveKit
        """
        if not self._connected or self._room is None:
            raise RuntimeError("Not connected to LiveKit. Call connect() first.")

        # Placeholder implementation - yields empty generator
        # In a real implementation, this would subscribe to the agent's
        # transcription/data track and yield text chunks as they arrive
        # For now, yields nothing until real implementation
        return
        yield  # Required for async generator

    @asynccontextmanager
    async def __aenter__(self) -> "VoiceSession":
        """Context manager entry - connects to LiveKit.

        Yields:
            Self for use in async context
        """
        await self.connect()
        try:
            yield self
        finally:
            await self.disconnect()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - disconnects from LiveKit."""
        await self.disconnect()
