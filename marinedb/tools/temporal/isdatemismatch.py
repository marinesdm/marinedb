
import re
from operator import itemgetter
from marinedb.utils import standardizenan
from marinedb.tools.temporal import splitdate

def _isempty(string):

    doesnotcontaindigit = re.sub(r'[^0-9]','',string)
    doesnotcontaindigit = (len(doesnotcontaindigit) == 0)

    return doesnotcontaindigit

def _isyearmismatch(datestr, yearstr):

    if not ((len(yearstr) == 2) or (len(yearstr) == 4)):
        return datestr, False

    mismatch = re.sub(yearstr, '', datestr)
    if len(mismatch) == len(datestr):

        if len(yearstr) == 2:
            return datestr, True

        mismatch = re.sub(yearstr[-2:], '', datestr)
        if len(mismatch) == len(datestr):
            return datestr, True

    return mismatch, False

def _ismonthmismatch(datestr, monthstr):

    if not ((len(monthstr) == 1) or (len(monthstr) == 2)):
        return datestr, False

    if len(monthstr) == 1:
        monthstr = "0" + monthstr

    mismatch = re.sub(monthstr, '', datestr)
    if len(mismatch) == len(datestr):

        mismatch = re.sub(mismatch[-1:], '', datestr)
        if len(mismatch) == len(datestr):
            return datestr, True

    return mismatch, False

def _isdaymismatch(datestr, daystr):

    if not ((len(daystr) == 1) or (len(daystr) == 2)):
        return datestr, False

    if len(daystr) == 1:
        daystr = "0" + daystr

    mismatch = re.sub(daystr, '', datestr)
    if len(mismatch) == len(datestr):

        mismatch = re.sub(mismatch[-1:], '', datestr)
        if len(mismatch) == len(datestr):
            return datestr, True

    return mismatch, False

def ismismatch_str(datestr, yearstr=None, monthstr=None, daystr=None):

    mismatch = datestr
    doesmismatch = False

    if (yearstr is not None) and (not pd.isnull(yearstr)):
        mismatch, doesmismatch = _isyearmismatch(datestr, yearstr)
        if doesmismatch or _isempty(mismatch):
            return doesmismatch

    if (monthstr is not None) and (not pd.isnull(monthstr)):
        mismatch, doesmismatch = _ismonthmismatch(mismatch, monthstr)
        if doesmismatch or _isempty(mismatch):
            return doesmismatch

    if (daystr is not None) and (not pd.isnull(daystr)):
        mismatch, doesmismatch = _isdaymismatch(mismatch, daystr)
        if doesmismatch or _isempty(mismatch):
            return doesmismatch

    return False

def ismismatch_raw(df, paramsK, paramsV):

    isdate = list(df[~pd.isnull(df[datekey])].index)

    for idx in isdate:
        tempparams = dict(zip(paramsK, df.loc[idx,paramsV].tolist()))
        doesmismatch = ismismatch_str(**tempparams)
        if doesmismatch:
            df.loc[idx,'issue_isdatemismatch'] = 'RECORDED_DATE_MISMATCH'

    return df

def ismismatch_ISO(df, paramsK, paramsV):

    columns = df.columns
    datekey = paramsV[paramsK.index('datestr')]
    isdate = (~pd.isnull(df[datekey]))
    subset = df[isdate].copy()

    subset = splitdate.apply(subset, datekey, split_type='all', drop_interval=True, inplace=False, flag=True)
    diffcolumns = list(set(subset.columns) - set(columns))

    yearkey = paramsV[paramsK.index('yearstr')]
    isyear = (~pd.isnull(subset[yearkey])) & (~pd.isnull(subset['year_processedby_splitdate']))
    doesmismatch = (subset.loc[isyear,yearkey] != subset.loc[isyear,'year_processedby_splitdate'])
    doesmismatch = doesmismatch[doesmismatch].index
    subset.loc[doesmismatch,'issue_isdatemismatch'] = 'RECORDED_DATE_MISMATCH'

    if 'monthstr' in paramsK:

        monthkey = paramsV[paramsK.index('monthstr')]
        ismonth = pd.isnull(subset['issue_isdatemismatch']) & (~pd.isnull(subset[monthkey])) & (~pd.isnull(subset['month_processedby_splitdate']))
        doesmismatch = (subset.loc[ismonth,monthkey] != subset.loc[ismonth,'month_processedby_splitdate'])
        doesmismatch = doesmismatch[doesmismatch].index
        subset.loc[doesmismatch,'issue_isdatemismatch'] = 'RECORDED_DATE_MISMATCH'

    if 'daystr' in paramsK:

        daykey = paramsV[paramsK.index('daystr')]
        isday = pd.isnull(subset['issue_isdatemismatch']) & (~pd.isnull(subset[daykey])) & (~pd.isnull(subset['day_processedby_splitdate']))
        doesmismatch = (subset.loc[isday,daykey] != subset.loc[isday,'day_processedby_splitdate'])
        doesmismatch = doesmismatch[doesmismatch].index
        subset.loc[doesmismatch,'issue_isdatemismatch'] = 'RECORDED_DATE_MISMATCH'

    subset.drop(columns=diffcolumns, inplace=True)

    df.loc[isdate,list(subset.columns)] = subset.values
    #QUE FAIRE INTERVALLES ? 
    return df

def apply(df, datekey, yearkey, monthkey=None, daykey=None, ISOformat=False, stdnan=True, cvttype=True):

    params = {"datestr" : datekey, "yearstr" : yearkey, "monthstr" : monthkey, "daystr" : daykey}
    params = {key : value for key, value in params.items() if value is not None}
    paramsK = list(params.keys())
    paramsV = list(itemgetter(*paramsK)(params))

    if stdnan:
        df = standardizenan.apply(df, key=paramsV)

    if cvttype:
        df = pdc.parse_year(df, yearkey)
        if monthkey is not None:
            df = pdc.parse_month(df, monthkey)
        if daykey is not None:
            df = pdc.parse_day(df, daykey)

    if ISOformat: #JE NE SUIS PAS SÛRE QUE CE SOIT PERTINENT ... OU BIEN VÉRIFIER SI DATE SLIT EXISTE DÉJÀ 
        df = ismismatch_ISO(df, paramsK, paramsV)
    else:
        df = ismismatch_raw(df, paramsK, paramsV)

    return df

