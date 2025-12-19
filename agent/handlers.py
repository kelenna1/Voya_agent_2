# agent/handlers.py
"""
Direct handlers for simple queries - NO LLM needed
Fast path that bypasses the agent completely
"""

import logging
from typing import Dict
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
                return {
                    'success': False,
                    'message': "No flights found for the selected route and date.",
                    'flights': [],
                    'search_params': params,
                    'handled_by': 'direct_handler'
                }

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

        except Exception:
            logger.exception("[Direct Handler] Flight search failed")
            return {
                'success': False,
                'message': "Unable to retrieve flight information at this time.",
                'flights': [],
                'handled_by': 'direct_handler'
            }

    def handle_tour_search(self, params: Dict) -> Dict:
        try:
            logger.info(
                f"[Direct Handler] Tour search: "
                f"{params.get('query')} in {params.get('destination')}"
            )

            tours = self.viator.search_tours(
                query=params.get('query', 'tour'),
                destination=params.get('destination'),
                start_date=params.get('date'),
                page_size=params.get('limit', 5)
            ) or []

            if not tours:
                return {
                    'success': False,
                    'message': "No tours found for this destination.",
                    'tours': [],
                    'destination': {'name': params.get('destination')},
                    'handled_by': 'direct_handler'
                }

            logger.info(f"[Direct Handler] Tour search completed: {len(tours)} results")

            return {
                'success': True,
                'message': f"Found {len(tours)} tours.",
                'tours': tours,
                'destination': {'name': params.get('destination')},
                'handled_by': 'direct_handler',
                'cached': False
            }

        except Exception:
            logger.exception("[Direct Handler] Tour search failed")
            return {
                'success': False,
                'message': "Unable to retrieve tours at this time.",
                'tours': [],
                'destination': {'name': params.get('destination')},
                'handled_by': 'direct_handler'
            }

    def handle_place_search(self, params: Dict) -> Dict:
        try:
            logger.info(f"[Direct Handler] Place search: {params.get('query')}")

            places = self.places.search_places(
                query=params.get('query'),
                limit=params.get('limit', 5)
            ) or []

            if not places:
                return {
                    'success': False,
                    'message': "No places found for this query.",
                    'places': [],
                    'handled_by': 'direct_handler'
                }

            logger.info(f"[Direct Handler] Place search completed: {len(places)} results")

            return {
                'success': True,
                'message': f"Found {len(places)} places.",
                'places': places,
                'handled_by': 'direct_handler',
                'cached': False
            }

        except Exception:
            logger.exception("[Direct Handler] Place search failed")
            return {
                'success': False,
                'message': "Unable to retrieve places at this time.",
                'places': [],
                'handled_by': 'direct_handler'
            }


# Singleton instance
_handlers = None


def get_handlers() -> DirectHandlers:
    """Get or create singleton handlers instance"""
    global _handlers
    if _handlers is None:
        _handlers = DirectHandlers()
    return _handlers

