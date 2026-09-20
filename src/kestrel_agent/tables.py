"""Bounded, deterministic queries over local CSV or JSON records; no code evaluation."""
import csv
import json
from decimal import Decimal, InvalidOperation, Inexact, localcontext
from pathlib import Path


def number(value):
    if isinstance(value, bool) or value is None:
        return None
    if len(str(value)) > 128:
        return None
    try:
        parsed=Decimal(str(value))
        return parsed if parsed.is_finite() and abs(parsed.adjusted()) <= 40 and len(parsed.as_tuple().digits) <= 40 else None
    except InvalidOperation:
        return None


def query(path: Path, args: dict) -> dict:
    with localcontext() as context:
        context.prec=80
        result=_query(path,args)
        result.update(decimal_precision=80,rounded=context.flags[Inexact])
        return result


def _query(path: Path, args: dict) -> dict:
    if path.stat().st_size > 5_000_000:
        raise ValueError('Table exceeds 5 MB; narrow the input.')
    if path.suffix.lower()=='.csv':
        with path.open(newline='',encoding='utf-8-sig') as stream:
            rows=list(csv.DictReader(stream))
    elif path.suffix.lower()=='.json':
        rows=json.loads(path.read_text())
    else:
        raise ValueError('query_table accepts CSV or a JSON array of records.')
    if not isinstance(rows,list) or len(rows)>20000 or not all(isinstance(row,dict) for row in rows):
        raise ValueError('Expected at most 20,000 object records.')
    columns={key for row in rows for key in row}
    group=args.get('group_by')
    value=args.get('value_column')
    operation=args.get('operation')
    if operation not in {'sum','mean','count','min','max'}:
        raise ValueError('Use sum, mean, count, min, or max.')
    if group is not None and group not in columns:
        raise ValueError('Unknown group_by column.')
    if operation!='count' and value not in columns:
        raise ValueError('Unknown value_column.')
    filters=args.get('filters',[])
    if not isinstance(filters,list) or len(filters)>16:
        raise ValueError('filters must contain at most 16 predicates.')
    for condition in filters:
        if not isinstance(condition,dict) or condition.get('column') not in columns or condition.get('op') not in {'eq','ne','gt','gte','lt','lte'} or 'value' not in condition:
            raise ValueError('Invalid column, comparison, or value in filter.')
    def matches(row):
        for condition in filters:
            column,op,expected=condition['column'],condition['op'],condition['value']
            if column not in row or row[column] is None:
                return False
            raw=row[column]
            if op in {'eq','ne'}:
                equal=str(raw)==str(expected)
                if (op=='eq' and not equal) or (op=='ne' and equal):
                    return False
            else:
                actual,target=number(raw),number(expected)
                if actual is None or target is None:
                    return False
                if not {'gt':actual>target,'gte':actual>=target,'lt':actual<target,'lte':actual<=target}[op]:
                    return False
        return True
    buckets={}
    matched=invalid=missing_group=0
    for row in rows:
        if not matches(row):
            continue
        matched+=1
        if group is not None and (group not in row or row[group] is None):
            missing_group+=1
            continue
        key=str(row[group]) if group else 'all'
        parsed=Decimal(1) if operation=='count' else number(row.get(value))
        if parsed is None:
            invalid+=1
            continue
        buckets.setdefault(key,[]).append(parsed)
        if len(buckets)>200:
            raise ValueError('More than 200 groups; narrow the query.')
    results={}
    for key,values in buckets.items():
        if operation=='count': result=Decimal(len(values))
        elif operation=='sum': result=sum(values,Decimal(0))
        elif operation=='mean': result=sum(values,Decimal(0))/len(values)
        elif operation=='min': result=min(values)
        else: result=max(values)
        # Preserve decimal precision in evidence rather than silently rounding to binary floats.
        results[key]=format(result,'f')
    return {'results':results,'operation':operation,'group_by':group,'value_column':value,
            'source_rows':len(rows),'matched_rows':matched,'invalid_numeric_rows_skipped':invalid,
            'missing_group_rows_skipped':missing_group,'numeric_encoding':'decimal strings','path':str(path)}
