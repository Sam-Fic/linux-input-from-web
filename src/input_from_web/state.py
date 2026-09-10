"""Mutable runtime settings shared by CLI bootstrap and Flask routes."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Runtime:
    token: str
    use_token: bool = True
    permanent_link: bool = False
    method: str = "type"
    auto_paste: bool = False
    paste_key: str = "ctrl+v"
    auto_press_enter: bool = False
    profile: dict = field(default_factory=dict)
    full_config: Optional[dict] = None
    current_profile_name: Optional[str] = None

    def persist_profile(self, save_config) -> None:
        if (
            self.full_config is not None
            and self.current_profile_name in self.full_config.get("profiles", {})
        ):
            self.full_config["profiles"][self.current_profile_name] = self.profile
            save_config(self.full_config)
