from __future__ import annotations

import unittest

from app.services.shs_section_renaming import _replace_section_in_key, section_name_for


class ShsSectionRenamingTests(unittest.TestCase):
    def test_all_approved_shs_track_cluster_names_are_mapped(self) -> None:
        expected = {
            ("Academic Track", "Arts, Social Sciences, and Humanities"): "Lualhati",
            ("Academic Track", "Science, Technology, Engineering, and Mathematics (STEM)"): "Mabini",
            ("Academic Track", "Sports, Health, and Wellness"): "Magiting",
            ("Academic Track", "Business and Entrepreneurship"): "Lakandula",
            ("Academic Track", "Field Experience"): "Malaya",
            ("Technical Professional (TechPro) Track", "Aesthetic, Wellness, and Human Care"): "Liwayway",
            ("Technical Professional (TechPro) Track", "Agri-Fishery Business and Food Innovation"): "Luntian",
            ("Technical Professional (TechPro) Track", "Artisanry and Creative Enterprise"): "Likha",
            ("Technical Professional (TechPro) Track", "Automotive and Small Engine Technologies"): "Lapu-Lapu",
            ("Technical Professional (TechPro) Track", "Construction and Building Technologies"): "Matibay",
            ("Technical Professional (TechPro) Track", "Creative Arts and Design Technologies"): "Hiraya",
            ("Technical Professional (TechPro) Track", "Hospitality and Tourism"): "Masigla",
            ("Technical Professional (TechPro) Track", "ICT Support and Computer Programming Technologies"): "Talino",
            ("Technical Professional (TechPro) Track", "Industrial Technologies"): "Masikap",
            ("Technical Professional (TechPro) Track", "Maritime"): "Mandaragat",
        }
        self.assertEqual(len(expected), 15)
        for (track, cluster), section_name in expected.items():
            with self.subTest(track=track, cluster=cluster):
                self.assertEqual(section_name_for(track, cluster), section_name)

    def test_class_key_replacement_updates_only_the_section_slug(self) -> None:
        self.assertEqual(
            _replace_section_in_key("2026-2027-q1-grade-11-section-academic-business-business-1", "Section Academic Business", "Lakandula"),
            "2026-2027-q1-grade-11-lakandula-business-1",
        )


if __name__ == "__main__":
    unittest.main()
