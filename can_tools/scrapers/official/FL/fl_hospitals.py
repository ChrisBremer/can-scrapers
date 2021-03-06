from abc import ABC

import pandas as pd
import pyppeteer
import us

from can_tools.scrapers.base import DatasetBase, CMU
from can_tools.scrapers.official.base import StateDashboard
from can_tools.scrapers.puppet import TableauNeedsClick


class FloridaHospitalUsage(TableauNeedsClick, ABC):
    """
    Fetch details about overall Florida hospital usage
    """

    url = "https://bi.ahca.myflorida.com/t/ABICC/views/Public/HospitalBedsHospital?:isGuestRedirectFromVizportal=y&:embed=y"

    async def _pre_click(self, page: pyppeteer.page.Page):
        await page.waitForSelector(".tabCanvas")

    def _clean_cols(self, df: pd.DataFrame, bads: list, str_cols: list) -> pd.DataFrame:
        for col in list(df):
            for bad in bads:
                df[col] = df[col].astype(str).str.replace(bad, "")
            if col not in str_cols:
                df[col] = pd.to_numeric(df[col])

        return df

    def _clean_df(self, df: pd.DataFrame) -> pd.DataFrame:
        bads = [r",", r"%", "nan"]
        str_cols = ["County", "FileNumber", "ProviderName"]
        df = self._clean_cols(df, bads, str_cols)
        df["county"] = df["County"].str.title()

        # Rename appropriate columns
        crename = {
            "Bed Census": CMU(
                category="hospital_beds_in_use", measurement="current", unit="beds"
            ),
            "Available": CMU(
                category="hospital_beds_available", measurement="current", unit="beds"
            ),
            "Total Staffed Bed Capacity": CMU(
                category="hospital_beds_capacity", measurement="current", unit="beds"
            ),
        }

        # Drop grand total and melt
        out = (
            df.query("county != 'Grand Total'")
            .melt(id_vars=["county"], value_vars=crename.keys())
            .dropna()
        )
        out["value"] = pd.to_numeric(out["value"])
        out = out.groupby(["county", "variable"]).sum().reset_index()

        # Extract category information and add other context
        out = self.extract_CMU(out, crename)

        out_cols = [
            "county",
            "category",
            "measurement",
            "unit",
            "age",
            "race",
            "sex",
            "value",
        ]

        return out.loc[:, out_cols]


class FloridaICUUsage(FloridaHospitalUsage, ABC):
    """
    Fetch ICU usage details from Tableau dashboard
    """

    url = "https://bi.ahca.myflorida.com/t/ABICC/views/Public/ICUBedsHospital?:isGuestRedirectFromVizportal=y&:embed=y"

    def _clean_df(self, df: pd.DataFrame) -> pd.DataFrame:
        bads = [r",", r"%", "nan"]
        str_cols = ["County", "FileNumber", "ProviderName"]
        df = self._clean_cols(df, bads, str_cols)
        df["county"] = df["County"].str.title()

        # Create new columns
        df["ICU Census"] = df["Adult ICU Census"] + df["Pediatric ICU Census"]
        df["ICU Capacity"] = (
            df["Total AdultICU Capacity"] + df["Total PediatricICU Capacity"]
        )
        df["Available ICU"] = df["Available Adult ICU"] + df["Available Pediatric ICU"]

        # Rename appropriate columns
        crename = {
            "Adult ICU Census": CMU(
                category="adult_icu_beds_in_use", measurement="current", unit="beds"
            ),
            "Available Adult ICU": CMU(
                category="adult_icu_beds_available", measurement="current", unit="beds"
            ),
            "Total AdultICU Capacity": CMU(
                category="adult_icu_beds_capacity", measurement="current", unit="beds"
            ),
            "Pediatric ICU Census": CMU(
                category="pediatric_icu_beds_in_use", measurement="current", unit="beds"
            ),
            "Available Pediatric ICU": CMU(
                category="pediatric_icu_beds_available",
                measurement="current",
                unit="beds",
            ),
            "Total PediatricICU Capacity": CMU(
                category="pediatric_icu_beds_capacity",
                measurement="current",
                unit="beds",
            ),
            "ICU Census": CMU(
                category="icu_beds_in_use", measurement="current", unit="beds"
            ),
            "ICU Capacity": CMU(
                category="icu_beds_capacity", measurement="current", unit="beds"
            ),
            "Available ICU": CMU(
                category="icu_beds_available", measurement="current", unit="beds"
            ),
        }

        # Drop grand total and melt
        out = (
            df.query("county != 'Grand Total'")
            .melt(id_vars=["county"], value_vars=crename.keys())
            .dropna()
        )
        out["value"] = pd.to_numeric(out["value"])
        out = out.groupby(["county", "variable"]).sum().reset_index()

        # Extract category information and add other context
        out = self.extract_CMU(out, crename)

        out_cols = [
            "county",
            "category",
            "measurement",
            "unit",
            "age",
            "race",
            "sex",
            "value",
        ]

        return out.loc[:, out_cols]


class FloridaHospitalCovid(TableauNeedsClick, ABC):
    """
    Fetch count of all hospital beds in use by covid patients
    """

    url = "https://bi.ahca.myflorida.com/t/ABICC/views/Public/COVIDHospitalizationsCounty?:isGuestRedirectFromVizportal=y&:embed=y"

    def _clean_df(self, df: pd.DataFrame) -> pd.DataFrame:
        # Clean up column names
        df.columns = ["county", "value"]
        df["county"] = df["county"].str.title()
        df = df.query("county != 'Grand Total'")

        # Covnert to numeric
        df["value"] = pd.to_numeric(df["value"].astype(str).str.replace(",", ""))

        # Set category/measurment/unit/age/sex/race
        df.loc[:, "category"] = "hospital_beds_in_use_covid"
        df.loc[:, "measurement"] = "current"
        df.loc[:, "unit"] = "beds"
        df.loc[:, "age"] = "all"
        df.loc[:, "sex"] = "all"
        df.loc[:, "race"] = "all"

        return df


class FloridaHospital(DatasetBaseNoDate, StateDashboard):
    """
    Fetch all data from florida hospitals tableau dashboard
    """

    source = "https://bi.ahca.myflorida.com/t/ABICC/views/Public/HospitalBedsCounty"
    has_location = False
    state_fips = int(us.states.lookup("Florida").fips)

    def get(self):
        fiu = FloridaICUUsage()
        fhu = FloridaHospitalUsage()
        fhc = FloridaHospitalCovid()
        today = self._retrieve_dt("US/Eastern")
        vintage = self._retrieve_vintage()

        return pd.concat(
            [fiu.get(), fhu.get(), fhc.get()], ignore_index=True, sort=True, axis=0
        ).assign(dt=today, vintage=vintage)
