def bitumen_quality_ai(penetration, softening_point, ductility):
    """
    Basic but industry-realistic rules
    VG-30 typical ranges (simplified)
    """

    if penetration < 50 or penetration > 70:
        return "FAIL", "Penetration out of acceptable range"

    if softening_point < 47:
        return "RISK", "Low softening point may cause rutting"

    if ductility < 75:
        return "RISK", "Low ductility – cracking risk"

    return "PASS", "All parameters within acceptable limits"
