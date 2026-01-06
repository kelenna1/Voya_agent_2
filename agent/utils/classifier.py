# agent/utils/classifier.py - FIXED
"""
Fast query classifier - NO LLM calls
Determines if query is simple (flight/tour/place) or complex (needs agent)
"""

import re
from datetime import datetime
from typing import Dict, Optional, List


class QueryClassifier:
    """Classify user queries without using LLM"""

    # Common airports - NOT exhaustive, just hints
    COMMON_AIRPORTS = {
        'lagos': 'LOS', 'abuja': 'ABV', 'kano': 'KAN', 'port harcourt': 'PHC',
        'dubai': 'DXB', 'abu dhabi': 'AUH', 'doha': 'DOH', 'riyadh': 'RUH',
        'london': 'LHR', 'paris': 'CDG', 'rome': 'FCO', 'amsterdam': 'AMS',
        'new york': 'JFK', 'los angeles': 'LAX', 'chicago': 'ORD',
        'istanbul': 'IST', 'cairo': 'CAI', 'johannesburg': 'JNB',
        'nairobi': 'NBO', 'accra': 'ACC', 'addis ababa': 'ADD'
    }

    FLIGHT_PATTERNS = [
        r'\b(flight|flights|fly|flying|plane|ticket|tickets)\b',
        r'\b(from|to|→|->)\b.*(to|from)\b',
        r'\b(depart|departure|leave|leaving|return|returning)\b',
        r'\b(one[- ]?way|round[- ]?trip|roundtrip)\b',
        r'\b(economy|business|first class|premium)\b'
    ]

    TOUR_PATTERNS = [
        r'\b(tour|tours|activity|activities|excursion|sightseeing)\b',
        r'\b(things to do|what to do|attractions|visit)\b',
        r'\b(museum|castle|palace|temple|church|monument)\b',
        r'\b(experience|adventure|safari|cruise)\b'
    ]

    PLACE_PATTERNS = [
        r'\b(hotel|hotels|accommodation|stay|resort|hostel)\b',
        r'\b(restaurant|restaurants|cafe|bar|dining|eat|food)\b',
        r'\b(near|close to|around)\b',
        r'\b(5[- ]?star|luxury|budget|cheap)\b'
    ]

    COMPLEX_INDICATORS = [
        r'\b(plan|planning|itinerary|schedule)\b',
        r'\b(compare|vs|versus|better|best)\b',
        r'\b(recommend|suggest|advice|opinion)\b',
        r'\b(and|also|then|after|before)\b.*\b(and|also|then|after|before)\b',
        r'\b\d+[- ]?(day|night|week)\b.*\b(trip|vacation|holiday)\b',
    ]

    @classmethod
    def classify(cls, query: str) -> Dict:
        query_lower = query.lower().strip()

        if cls._is_complex_query(query_lower):
            return {
                'type': 'complex',
                'confidence': 0.9,
                'params': {},
                'use_agent': True,
                'reason': 'Multi-step reasoning required'
            }

        flight_score = cls._score_patterns(query_lower, cls.FLIGHT_PATTERNS)
        tour_score = cls._score_patterns(query_lower, cls.TOUR_PATTERNS)
        place_score = cls._score_patterns(query_lower, cls.PLACE_PATTERNS)

        scores = {
            'flight': flight_score,
            'tour': tour_score,
            'place': place_score
        }

        max_type = max(scores, key=scores.get)
        max_score = scores[max_type]

        if max_score < 1:
            return {
                'type': 'unknown',
                'confidence': 0.0,
                'params': {},
                'use_agent': True,
                'reason': 'Query type unclear'
            }

        if max_type == 'flight':
            params = cls._extract_flight_params(query_lower)
            pattern_len = len(cls.FLIGHT_PATTERNS)
        elif max_type == 'tour':
            params = cls._extract_tour_params(query_lower)
            pattern_len = len(cls.TOUR_PATTERNS)
        else:
            params = cls._extract_place_params(query_lower)
            pattern_len = len(cls.PLACE_PATTERNS)

        required_params = cls._get_required_params(max_type)
        missing = [p for p in required_params if not params.get(p)]

        confidence = max_score / pattern_len

        # ✅ FIX: If extraction failed or looks wrong, use agent
        if missing or cls._params_look_invalid(params, max_type):
            return {
                'type': max_type,
                'confidence': confidence,
                'params': params,
                'use_agent': True,  # Let agent handle it
                'reason': f'Params unclear or missing: {missing}'
            }

        return {
            'type': max_type,
            'confidence': confidence,
            'params': params,
            'use_agent': False,
            'reason': 'All required params extracted'
        }

    @classmethod
    def _params_look_invalid(cls, params: Dict, query_type: str) -> bool:
        """Check if extracted params look wrong"""
        if query_type == 'tour':
            dest = params.get('destination', '')
            # Check if destination has weird patterns
            if not dest or len(dest) < 3:
                return True
            # Check for leftover words like "to", "from", etc.
            if any(word in dest.lower() for word in ['to ', ' to', 'from ', ' from']):
                return True
        
        elif query_type == 'flight':
            origin = params.get('origin')
            dest = params.get('destination')
            # If either is missing or invalid
            if not origin or not dest or len(origin) != 3 or len(dest) != 3:
                return True
        
        return False

    @classmethod
    def _is_complex_query(cls, query: str) -> bool:
        matches = sum(1 for p in cls.COMPLEX_INDICATORS if re.search(p, query))

        if matches >= 2:
            intent_score = (
                cls._score_patterns(query, cls.FLIGHT_PATTERNS) +
                cls._score_patterns(query, cls.TOUR_PATTERNS) +
                cls._score_patterns(query, cls.PLACE_PATTERNS)
            )
            return intent_score < 2

        return False

    @classmethod
    def _score_patterns(cls, query: str, patterns: List[str]) -> int:
        return sum(1 for p in patterns if re.search(p, query))

    @classmethod
    def _extract_flight_params(cls, query: str) -> Dict:
        params = {}

        origin, destination = cls._extract_route(query)
        if origin:
            params['origin'] = origin
        if destination:
            params['destination'] = destination

        date_info = cls._extract_dates(query)
        if date_info.get('departure'):
            params['departure_date'] = date_info['departure']

        cabin = cls._extract_cabin_class(query)
        if cabin:
            params['cabin_class'] = cabin

        params['adults'] = cls._extract_passenger_count(query)
        params['limit'] = 5

        return params

    @classmethod
    def _extract_tour_params(cls, query: str) -> Dict:
        """Extract tour parameters - FIXED to handle edge cases"""
        params = {}

        destination = cls._extract_destination(query)
        if destination:
            # Clean up the destination
            destination = destination.strip()
            
            # Remove trailing prepositions/words
            for suffix in [' to', ' from', ' in', ' at', ' on']:
                if destination.endswith(suffix):
                    destination = destination[:-len(suffix)].strip()
            
            # Only set if it's a valid city name
            if len(destination) >= 3 and destination.replace(' ', '').isalpha():
                params['destination'] = destination
            else:
                # Invalid destination - let agent handle it
                params['destination'] = None

        params['limit'] = 5
        return params

    @classmethod
    def _extract_place_params(cls, query: str) -> Dict:
        """Extract place parameters - FIXED"""
        params = {}

        destination = cls._extract_destination(query)
        if destination:
            # Clean up
            destination = destination.strip()
            for suffix in [' to', ' from', ' in', ' at']:
                if destination.endswith(suffix):
                    destination = destination[:-len(suffix)].strip()
            
            if len(destination) >= 3:
                params['query'] = destination
            else:
                params['query'] = query  # fallback to full query
        else:
            params['query'] = query

        params['limit'] = 5
        return params

    @classmethod
    def _extract_route(cls, query: str) -> tuple:
        """Extract flight route - MORE STRICT"""
        patterns = [
            # "from X to Y"
            r'from\s+([a-z\s]+?)\s+to\s+([a-z\s]+?)(?:\s+on|\s+for|\s+return|\s+next|\s+tomorrow|\s*$)',
            # "X to Y"
            r'\b([a-z\s]+?)\s+to\s+([a-z\s]+?)(?:\s+on|\s+for|\s+next|\s+tomorrow|\s*$)',
        ]

        for pattern in patterns:
            match = re.search(pattern, query)
            if match:
                origin_text = match.group(1).strip()
                dest_text = match.group(2).strip()
                
                # Try to convert to airport codes
                origin = cls._to_airport_code(origin_text)
                destination = cls._to_airport_code(dest_text)
                
                if origin and destination:
                    return origin, destination

        return None, None

    @classmethod
    def _to_airport_code(cls, city: str) -> Optional[str]:
        """Convert city name to airport code - MORE FLEXIBLE"""
        city = city.lower().strip()
        
        # If already a 3-letter code
        if len(city) == 3 and city.isalpha():
            return city.upper()
        
        # Check common airports
        if city in cls.COMMON_AIRPORTS:
            return cls.COMMON_AIRPORTS[city]
        
        # ✅ If not in our list, return None (let agent handle it)
        return None

    @classmethod
    def _extract_destination(cls, query: str) -> Optional[str]:
        """Extract destination for tours/places - FIXED TO BE MORE PRECISE"""
        # Try multiple patterns in order of specificity
        patterns = [
            # "in [City]" or "at [City]"
            r'\b(?:in|at)\s+([a-z]+(?:\s+[a-z]+)?)\b',
            # "to [City]" (but stop at prepositions)
            r'\bto\s+([a-z]+)\b(?!\s+(?:see|do|visit|find|get))',
        ]

        for pattern in patterns:
            match = re.search(pattern, query)
            if match:
                destination = match.group(1).strip()
                
                # Filter out common non-destinations
                if destination not in ['see', 'do', 'get', 'find', 'go', 'visit', 'the']:
                    return destination

        return None

    @classmethod
    def _extract_dates(cls, query: str) -> Dict:
        dates = {}
        today = datetime.now()

        month_map = {
            'jan': 1, 'january': 1, 'feb': 2, 'february': 2,
            'mar': 3, 'march': 3, 'apr': 4, 'april': 4,
            'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
            'aug': 8, 'august': 8, 'sep': 9, 'sept': 9, 'september': 9,
            'oct': 10, 'october': 10, 'nov': 11, 'november': 11,
            'dec': 12, 'december': 12
        }

        match = re.search(
            r'(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)',
            query
        )

        if match:
            day, month_str = match.groups()
            month = month_map[month_str]
            year = today.year
            date_obj = datetime(year, month, int(day))
            if date_obj.date() < today.date():
                date_obj = datetime(year + 1, month, int(day))
            dates['departure'] = date_obj.strftime('%Y-%m-%d')

        return dates

    @classmethod
    def _extract_cabin_class(cls, query: str) -> Optional[str]:
        if re.search(r'\bbusiness\b', query):
            return 'BUSINESS'
        if re.search(r'\bfirst\b', query):
            return 'FIRST'
        if re.search(r'\bpremium\b', query):
            return 'PREMIUM_ECONOMY'
        return None

    @classmethod
    def _extract_passenger_count(cls, query: str) -> int:
        match = re.search(r'(\d+)\s+(?:passengers|people|adults)', query)
        return int(match.group(1)) if match else 1

    @classmethod
    def _get_required_params(cls, query_type: str) -> List[str]:
        return {
            'flight': ['origin', 'destination', 'departure_date'],
            'tour': ['destination'],
            'place': ['query']
        }.get(query_type, [])