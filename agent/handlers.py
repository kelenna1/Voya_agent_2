# agent/handlers.py - FIXED with proper fallback
"""
Direct handlers for simple queries - NO LLM needed
Fast path that bypasses the agent completely

If extraction fails or service errors occur, these handlers return
a special flag to trigger agent fallback.
"""

import logging
from typing import Dict, Optional
from agent.services.mistifly import MistiflyService
from agent.services.viator import ViatorService
from agent.services.google import GooglePlacesService

logger = logging.getLogger(__name__)


class DirectHandlers:
    """Handle simple queries without using the agent"""

    def __init__(self):
        self.mistifly = MistiflyService()
        self.viator = ViatorService()
        self.places = GooglePlacesService()

    def handle_flight_search(self, params: Dict) -> Dict:
        """Handle flight search - returns fallback flag on failure"""
        try:
            logger.info(
                f"[Direct Handler] Flight search: "
                f"{params.get('origin')} -> {params.get('destination')}"
            )

            flights = self.mistifly.search_flights(
                origin=params.get('origin'),
                destination=params.get('destination'),
                departure_date=params.get('departure_date'),
                return_date=params.get('return_date'),
                adults=params.get('adults', 1),
                cabin_class=params.get('cabin_class', 'ECONOMY'),
                limit=params.get('limit', 5)
            ) or []

            if not flights:
                logger.warning("[Direct Handler] No flights found - triggering agent fallback")
                return self._create_agent_fallback('flight', 'No flights found')

            search_params = {
                'origin': params.get('origin'),
                'destination': params.get('destination'),
                'departure_date': params.get('departure_date'),
                'return_date': params.get('return_date'),
                'passengers': params.get('adults', 1)
            }

            for flight in flights:
                if isinstance(flight, dict):
                    flight['search_params'] = search_params

            logger.info(f"[Direct Handler] Flight search completed: {len(flights)} results")

            return {
                'success': True,
                'message': f"Found {len(flights)} flights.",
                'flights': flights,
                'search_params': search_params,
                'handled_by': 'direct_handler',
                'cached': False
            }

        except Exception as e:
            logger.exception("[Direct Handler] Flight search failed - triggering agent fallback")
            return self._create_agent_fallback('flight', str(e))

    def handle_tour_search(self, params: Dict) -> Dict:
        """Handle tour search - returns fallback flag on failure"""
        try:
            destination = params.get('destination')
            
            # ✅ Validate destination before calling service
            if not destination or len(destination) < 3:
                logger.warning(f"[Direct Handler] Invalid destination '{destination}' - triggering agent fallback")
                return self._create_agent_fallback('tour', 'Invalid destination extracted')
            
            logger.info(
                f"[Direct Handler] Tour search: "
                f"{params.get('query', 'tour')} in {destination}"
            )

            tours = self.viator.search_tours(
                query=params.get('query', 'tour'),
                destination=destination,
                start_date=params.get('date'),
                page_size=params.get('limit', 5)
            ) or []

            if not tours:
                logger.warning(f"[Direct Handler] No tours found in {destination} - triggering agent fallback")
                return self._create_agent_fallback('tour', f'No tours found in {destination}')

            logger.info(f"[Direct Handler] Tour search completed: {len(tours)} results")

            return {
                'success': True,
                'message': f"Found {len(tours)} tours.",
                'tours': tours,
                'destination': {'name': destination},
                'handled_by': 'direct_handler',
                'cached': False
            }

        except Exception as e:
            logger.exception(f"[Direct Handler] Tour search failed: {e} - triggering agent fallback")
            return self._create_agent_fallback('tour', str(e))

    def handle_place_search(self, params: Dict) -> Dict:
        """Handle place search - returns fallback flag on failure"""
        try:
            query = params.get('query')
            
            if not query or len(query) < 3:
                logger.warning(f"[Direct Handler] Invalid query '{query}' - triggering agent fallback")
                return self._create_agent_fallback('place', 'Invalid query extracted')
            
            logger.info(f"[Direct Handler] Place search: {query}")

            places = self.places.search_places(
                query=query,
                limit=params.get('limit', 5)
            ) or []

            if not places:
                logger.warning(f"[Direct Handler] No places found for '{query}' - triggering agent fallback")
                return self._create_agent_fallback('place', f'No places found for {query}')

            logger.info(f"[Direct Handler] Place search completed: {len(places)} results")

            return {
                'success': True,
                'message': f"Found {len(places)} places.",
                'places': places,
                'handled_by': 'direct_handler',
                'cached': False
            }

        except Exception as e:
            logger.exception(f"[Direct Handler] Place search failed: {e} - triggering agent fallback")
            return self._create_agent_fallback('place', str(e))

    @staticmethod
    def _create_agent_fallback(query_type: str, reason: str) -> Dict:
        """
        Create a special response that signals the view to use the agent instead
        """
        return {
            '_use_agent_fallback': True,  # Special flag
            'query_type': query_type,
            'reason': reason,
            'message': f'Direct handler failed for {query_type}: {reason}'
        }


# Singleton instance
_handlers = None


def get_handlers() -> DirectHandlers:
    """Get or create singleton handlers instance"""
    global _handlers
    if _handlers is None:
        _handlers = DirectHandlers()
    return _handlers