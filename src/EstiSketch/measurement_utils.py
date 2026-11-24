import re


class MeasurementConverter:
    @staticmethod
    def parse_measurement(input_val):
        if isinstance(input_val, (int, float)):
            return float(input_val)
        if isinstance(input_val, str):
            if "'" in input_val:
                pattern = r"^\s*(\d+)\s*'\s*(?:(\d+(?:\.\d+)?)(?:\s*(\d+/\d+))?)?\s*(?:\"|$)"
                m = re.match(pattern, input_val)
                if m:
                    feet = float(m.group(1))
                    inches_val = float(m.group(2)) if m.group(2) else 0.0
                    if m.group(3):
                        num, den = m.group(3).split("/")
                        inches_val += float(num) / float(den)
                    return feet * 12 + inches_val
                numbers = re.findall(r"[\d\.]+", input_val)
                if numbers:
                    feet = float(numbers[0])
                    inches_val = float(numbers[1]) if len(numbers) > 1 else 0.0
                    return feet * 12 + inches_val
            else:
                try:
                    return float(input_val)
                except Exception:
                    raise ValueError("Invalid measurement format.")
        raise ValueError("Unsupported measurement input type.")

    @staticmethod
    def format_measurement(inches, use_fraction=False):
        feet = int(inches // 12)
        remaining_inches = inches - (feet * 12)
        if use_fraction:
            frac_den = 8
            whole_inches = int(remaining_inches)
            frac = remaining_inches - whole_inches
            rounded_frac = round(frac * frac_den) / frac_den
            if rounded_frac >= 1.0:
                whole_inches += 1
                rounded_frac = 0.0
            if whole_inches >= 12:
                feet += whole_inches // 12
                whole_inches %= 12
            frac_str = ""
            if rounded_frac > 0:
                num = int(round(rounded_frac * frac_den))
                frac_str = f" {num}/{frac_den}"
            return f"{feet}' {whole_inches}{frac_str}\""
        else:
            rounded_inches = round(remaining_inches, 2)
            if rounded_inches >= 12.0:
                feet += 1
                rounded_inches = 0.0
            return f"{feet}' {rounded_inches}\""


_METRIC_UNITS = {"mm": 1 / 25.4, "cm": 1 / 2.54, "m": 100 / 2.54}


def parse_distance(text: str) -> float:
    """Parse a user-typed distance into inches.

    Accepts imperial (``24' 0"``, ``24'``, ``288``, ``288"``) and metric
    (``7500 mm``, ``750 cm``, ``7.5 m``) input. Plain numbers are inches.
    Raises ``ValueError`` for empty, malformed or non-positive values.
    """
    if text is None or not str(text).strip():
        raise ValueError("Enter a distance.")
    s = str(text).strip().lower()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(mm|cm|m)", s)
    if m:
        value = float(m.group(1)) * _METRIC_UNITS[m.group(2)]
    else:
        if s.endswith('"') and "'" not in s:
            s = s[:-1].strip()
        value = MeasurementConverter.parse_measurement(s)
    if value <= 0:
        raise ValueError("Distance must be greater than zero.")
    return value
