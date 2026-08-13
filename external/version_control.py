import re


def get_version(origin_ver: str) -> dict | str:
    if origin_ver is None or origin_ver == "":
        origin_ver = "1.0.0.0"
        return origin_ver
    version = re.compile(r"\.").split(origin_ver)
    try:

        minor_version = int(version[3])
        revise = int(version[2])
        critical_revise = int(version[1])
        phase = int(version[0])
    except IndexError:
        phase = 1
        critical_revise = 0
        revise = 0
        minor_version = -1
        
    return {
        "phase": phase,
        "critical_revise": critical_revise,
        "revise": revise,
        "minor_version": minor_version
    }
    



def update_version(version: dict | str) -> str:

    if isinstance(version, str):
        # what ? expect anything 
        return version

    carry_bit_minor_version = int((version["minor_version"] + 1) / 100)
    carry_bit_revise = int((version["revise"] + 1) / 100)
    carry_bit_critical_revise = int((version["critical_revise"] + 1) / 100)

    version["critical_revise"] += carry_bit_revise & carry_bit_minor_version
    version["critical_revise"] %= 100
    critical_revise = str(version["critical_revise"])

    version["revise"] += carry_bit_minor_version
    version["revise"] %= 100
    revise = str(version["revise"])

    version["minor_version"] = (version["minor_version"] + 1)
    version["minor_version"] %= 100
    minor_version = str(version["minor_version"])

    ver: list[str] = [
        str(version["phase"]),
        critical_revise, revise, minor_version]

    join_char = "."
    update_version = join_char.join(ver)

    # "phase" should be manually modify
    if carry_bit_minor_version and carry_bit_revise and carry_bit_critical_revise:
        print(
            "version is out of range,"
            "please manually update version member <phase> "
            "or redesign the control logic.")
        
    return update_version
    



def version_action(origin_ver: str) -> str:
    return update_version(get_version(origin_ver))
    
