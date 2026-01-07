# agent/utils/output_parser.py - NEW FILE
"""
Output parser to ensure consistent JSON responses from both agent and direct handlers
"""

import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class AgentOutputParser:
    """Parse and normalize agent outputs to match direct handler format"""
    
    @staticmethod
    def parse(agent_output: str) -> Optional[Dict[str, Any]]:
        """
        Parse agent output and return structured JSON
        
        Returns:
            - Dict if JSON found
            - None if no JSON found
        """
        # Try multiple extraction strategies
        strategies = [
            AgentOutputParser._extract_prefixed_json,
            AgentOutputParser._extract_embedded_json,
            AgentOutputParser._extract_pure_json,
        ]
        
        for strategy in strategies:
            result = strategy(agent_output)
            if result:
                # Normalize the structure
                return AgentOutputParser._normalize_structure(result)
        
        return None
    
    @staticmethod
    def _extract_prefixed_json(text: str) -> Optional[Dict]:
        """Extract JSON after known prefixes like 'FLIGHT_SEARCH_RESULT:'"""
        prefixes = [
            "TOUR_SEARCH_RESULT:",
            "PLACES_SEARCH_RESULT:",
            "PLACE_DETAILS_RESULT:",
            "FLIGHT_SEARCH_RESULT:",
            "FLIGHT_PRICE_RESULT:",
            "FLIGHT_BOOKING_RESULT:",
        ]
        
        for prefix in prefixes:
            if prefix in text:
                try:
                    json_start = text.find(prefix) + len(prefix)
                    json_part = text[json_start:].strip()
                    
                    # Find matching closing brace
                    brace_count = 0
                    json_end = 0
                    for i, char in enumerate(json_part):
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                json_end = i + 1
                                break
                    
                    if json_end > 0:
                        json_str = json_part[:json_end]
                        return json.loads(json_str)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.debug(f"Failed to parse prefixed JSON: {e}")
                    continue
        
        return None
    
    @staticmethod
    def _extract_embedded_json(text: str) -> Optional[Dict]:
        """Extract JSON embedded in text using regex"""
        import re
        
        # Pattern to match JSON objects
        pattern = r'\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\}))*\}))*\}'
        
        matches = re.finditer(pattern, text, re.DOTALL)
        
        for match in matches:
            try:
                json_str = match.group(0)
                parsed = json.loads(json_str)
                
                # Validate it looks like a valid response
                if any(key in parsed for key in ['success', 'flights', 'tours', 'places', 'message']):
                    return parsed
            except json.JSONDecodeError:
                continue
        
        return None
    
    @staticmethod
    def _extract_pure_json(text: str) -> Optional[Dict]:
        """Try to parse entire text as JSON"""
        text = text.strip()
        
        if text.startswith('{') and text.endswith('}'):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        
        return None
    
    @staticmethod
    def _normalize_structure(data: Dict) -> Dict:
        """
        Normalize the structure to match direct handler format
        Ensures consistent field names and types
        """
        normalized = {
            'success': data.get('success', True),
            'message': data.get('message', ''),
        }
        
        # Detect response type and include appropriate fields
        if 'flights' in data:
            normalized['type'] = 'flight_search'
            normalized['flights'] = data['flights']
            normalized['search_params'] = data.get('search_params', {})
            
        elif 'tours' in data:
            normalized['type'] = 'tour_search'
            normalized['tours'] = data['tours']
            normalized['destination'] = data.get('destination', {})
            
        elif 'places' in data:
            normalized['type'] = 'place_search'
            normalized['places'] = data['places']
            
        elif 'itinerary' in data:
            # Itinerary/complete trip responses
            normalized['type'] = 'itinerary'
            normalized['itinerary'] = data['itinerary']
            # Preserve any additional itinerary context if present
            for key in ['segments', 'flights', 'hotels', 'activities', 'trip']:
                if key in data and key not in normalized:
                    normalized[key] = data[key]
            
        elif 'booking' in data:
            normalized['type'] = 'booking'
            normalized['booking'] = data['booking']
            normalized['payment'] = data.get('payment', {})
            
        else:
            # Generic response
            normalized['type'] = 'conversational'
            normalized['output'] = data.get('output', data.get('message', ''))
        
        # Preserve other fields
        for key, value in data.items():
            if key not in normalized:
                normalized[key] = value
        
        return normalized


# Convenience function
def parse_agent_output(output: str) -> Dict[str, Any]:
    """
    Parse agent output and return structured response
    
    If parsing fails, wraps in a conversational response
    """
    result = AgentOutputParser.parse(output)
    
    if result:
        return result
    
    # Fallback: wrap in conversational structure
    return {
        'success': True,
        'type': 'conversational',
        'message': output,
        'output': output
    }