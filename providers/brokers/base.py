"""Abstract Base Class for Broker Providers.

Defines the contract for interacting with external brokerage platforms
such as Zerodha Kite, INDmoney, Groww, and Upstox.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BrokerProvider(ABC):
    """Abstract base provider defining standardized async broker integration methods."""

    def __init__(self, credentials: Optional[Dict[str, Any]] = None) -> None:
        """Initialize provider with optional authentication credentials or tokens."""
        self.credentials = credentials or {}

    @abstractmethod
    async def connect(self, credentials: Optional[Dict[str, Any]] = None) -> bool:
        """Authenticate or establish active session with the broker platform.

        Args:
            credentials: Optional override credentials (e.g. api_key, access_token).

        Returns:
            True if session is active and verified, False otherwise.
        """
        pass

    @abstractmethod
    async def get_account_status(self) -> Dict[str, Any]:
        """Fetch broker account status and profile metadata.

        Returns:
            Raw broker account profile and status dictionary.
        """
        pass

    @abstractmethod
    async def get_holdings(self) -> List[Dict[str, Any]]:
        """Fetch raw current portfolio holdings from the broker.

        Returns:
            List of raw holding entity dictionaries as returned by the broker API.
        """
        pass

    @abstractmethod
    async def get_transactions(self) -> List[Dict[str, Any]]:
        """Fetch raw transaction and trade history from the broker.

        Returns:
            List of raw trade/order dictionaries as returned by the broker API.
        """
        pass
