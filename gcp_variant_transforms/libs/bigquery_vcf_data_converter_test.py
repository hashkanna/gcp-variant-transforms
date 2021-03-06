# Copyright 2018 Google Inc.  All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for `bigquery_vcf_data_converter` module."""

from __future__ import absolute_import

import json
import unittest
from typing import Dict  # pylint: disable=unused-import

from apache_beam.io.gcp.internal.clients import bigquery

import mock

from gcp_variant_transforms.beam_io import vcfio
from gcp_variant_transforms.libs import bigquery_sanitizer
from gcp_variant_transforms.libs import bigquery_schema_descriptor
from gcp_variant_transforms.libs import bigquery_vcf_data_converter
from gcp_variant_transforms.libs import processed_variant
from gcp_variant_transforms.libs import vcf_field_conflict_resolver
from gcp_variant_transforms.libs.bigquery_util import ColumnKeyConstants
from gcp_variant_transforms.libs.bigquery_util import TableFieldConstants
from gcp_variant_transforms.libs.variant_merge import variant_merge_strategy
from gcp_variant_transforms.testing import vcf_header_util


def _get_processed_variant(variant, header_num_dict=None):
  # TODO(bashir2): To make this more of a "unit" test, we should create
  # ProcessedVariant instances directly (instead of Variant) and avoid calling
  # create_processed_variant here. Then we should also add cases that
  # have annotation fields.
  header_fields = vcf_header_util.make_header(header_num_dict or {})
  return processed_variant.ProcessedVariantFactory(
      header_fields).create_processed_variant(variant)


# TODO(allieychen): Use the sample schema in script `bigquery_schema_util`.
def _get_table_schema():
  # type (None) -> bigquery.TableSchema
  schema = bigquery.TableSchema()
  schema.fields.append(bigquery.TableFieldSchema(
      name='IB',
      type=TableFieldConstants.TYPE_BOOLEAN,
      mode=TableFieldConstants.MODE_NULLABLE,
      description='INFO foo desc'))
  schema.fields.append(bigquery.TableFieldSchema(
      name='IBR',
      type=TableFieldConstants.TYPE_BOOLEAN,
      mode=TableFieldConstants.MODE_REPEATED,
      description='INFO foo desc'))
  schema.fields.append(bigquery.TableFieldSchema(
      name='II',
      type=TableFieldConstants.TYPE_INTEGER,
      mode=TableFieldConstants.MODE_NULLABLE,
      description='INFO foo desc'))
  schema.fields.append(bigquery.TableFieldSchema(
      name='II2',
      type=TableFieldConstants.TYPE_INTEGER,
      mode=TableFieldConstants.MODE_NULLABLE,
      description='INFO foo desc'))
  schema.fields.append(bigquery.TableFieldSchema(
      name='IIR',
      type=TableFieldConstants.TYPE_INTEGER,
      mode=TableFieldConstants.MODE_REPEATED,
      description='INFO foo desc'))
  schema.fields.append(bigquery.TableFieldSchema(
      name='IF',
      type=TableFieldConstants.TYPE_FLOAT,
      mode=TableFieldConstants.MODE_NULLABLE,
      description='INFO foo desc'))
  schema.fields.append(bigquery.TableFieldSchema(
      name='IF2',
      type=TableFieldConstants.TYPE_FLOAT,
      mode=TableFieldConstants.MODE_NULLABLE,
      description='INFO foo desc'))
  schema.fields.append(bigquery.TableFieldSchema(
      name='IFR',
      type=TableFieldConstants.TYPE_FLOAT,
      mode=TableFieldConstants.MODE_REPEATED,
      description='INFO foo desc'))
  schema.fields.append(bigquery.TableFieldSchema(
      name='IFR2',
      type=TableFieldConstants.TYPE_FLOAT,
      mode=TableFieldConstants.MODE_REPEATED,
      description='INFO foo desc'))
  schema.fields.append(bigquery.TableFieldSchema(
      name='field__IS',
      type=TableFieldConstants.TYPE_STRING,
      mode=TableFieldConstants.MODE_NULLABLE,
      description='INFO foo desc'))
  schema.fields.append(bigquery.TableFieldSchema(
      name='IS',
      type=TableFieldConstants.TYPE_STRING,
      mode=TableFieldConstants.MODE_NULLABLE,
      description='INFO foo desc'))
  schema.fields.append(bigquery.TableFieldSchema(
      name='ISR',
      type=TableFieldConstants.TYPE_STRING,
      mode=TableFieldConstants.MODE_REPEATED,
      description='INFO foo desc'))
  # Call record.
  call_record = bigquery.TableFieldSchema(
      name=ColumnKeyConstants.CALLS,
      type=TableFieldConstants.TYPE_RECORD,
      mode=TableFieldConstants.MODE_REPEATED,
      description='One record for each call.')
  call_record.fields.append(bigquery.TableFieldSchema(
      name='FB',
      type=TableFieldConstants.TYPE_BOOLEAN,
      mode=TableFieldConstants.MODE_NULLABLE,
      description='FORMAT foo desc'))
  call_record.fields.append(bigquery.TableFieldSchema(
      name='FI',
      type=TableFieldConstants.TYPE_INTEGER,
      mode=TableFieldConstants.MODE_NULLABLE,
      description='FORMAT foo desc'))
  call_record.fields.append(bigquery.TableFieldSchema(
      name='GQ',
      type=TableFieldConstants.TYPE_INTEGER,
      mode=TableFieldConstants.MODE_NULLABLE,
      description='FORMAT foo desc'))
  call_record.fields.append(bigquery.TableFieldSchema(
      name='FIR',
      type=TableFieldConstants.TYPE_INTEGER,
      mode=TableFieldConstants.MODE_REPEATED,
      description='FORMAT foo desc'))
  call_record.fields.append(bigquery.TableFieldSchema(
      name='FSR',
      type=TableFieldConstants.TYPE_STRING,
      mode=TableFieldConstants.MODE_REPEATED,
      description='FORMAT foo desc'))
  schema.fields.append(call_record)
  return schema


def _get_big_query_row():
  # type: (None) -> Dict[unicode, Any]
  """Returns one sample BigQuery row for testing."""
  return {unicode(ColumnKeyConstants.REFERENCE_NAME): unicode('chr19'),
          unicode(ColumnKeyConstants.START_POSITION): 11,
          unicode(ColumnKeyConstants.END_POSITION): 12,
          unicode(ColumnKeyConstants.REFERENCE_BASES): 'C',
          unicode(ColumnKeyConstants.NAMES): [unicode('rs1'), unicode('rs2')],
          unicode(ColumnKeyConstants.QUALITY): 2,
          unicode(ColumnKeyConstants.FILTER): [unicode('PASS')],
          unicode(ColumnKeyConstants.CALLS): [
              {unicode(ColumnKeyConstants.CALLS_NAME): unicode('Sample1'),
               unicode(ColumnKeyConstants.CALLS_GENOTYPE): [0, 1],
               unicode(ColumnKeyConstants.CALLS_PHASESET): unicode('*'),
               unicode('GQ'): 20, unicode('FIR'): [10, 20]},
              {unicode(ColumnKeyConstants.CALLS_NAME): unicode('Sample2'),
               unicode(ColumnKeyConstants.CALLS_GENOTYPE): [1, 0],
               unicode(ColumnKeyConstants.CALLS_PHASESET): None,
               unicode('GQ'): 10, unicode('FB'): True}
          ],
          unicode(ColumnKeyConstants.ALTERNATE_BASES): [
              {unicode(ColumnKeyConstants.ALTERNATE_BASES_ALT): unicode('A'),
               unicode('IFR'): 1,
               unicode('IFR2'): 0.2},
              {unicode(ColumnKeyConstants.ALTERNATE_BASES_ALT): unicode('TT'),
               unicode('IFR'): 0.2,
               unicode('IFR2'): 0.3}
          ],
          unicode('IS'): unicode('some data'),
          unicode('ISR'): [unicode('data1'), unicode('data2')]}


class _DummyVariantMergeStrategy(variant_merge_strategy.VariantMergeStrategy):
  """A dummy strategy. It just adds a new field to the schema."""

  def modify_bigquery_schema(self, schema, info_keys):
    schema.fields.append(bigquery.TableFieldSchema(
        name='ADDED_BY_MERGER',
        type=TableFieldConstants.TYPE_STRING,
        mode=TableFieldConstants.MODE_NULLABLE))


class BigQueryRowGeneratorTest(unittest.TestCase):
  """Test cases for class ``BigQueryRowGenerator``."""

  def setUp(self):
    self._schema_descriptor = bigquery_schema_descriptor.SchemaDescriptor(
        _get_table_schema())
    self._conflict_resolver = (
        vcf_field_conflict_resolver.FieldConflictResolver())

    self._row_generator = bigquery_vcf_data_converter.BigQueryRowGenerator(
        self._schema_descriptor, self._conflict_resolver)

  def test_all_fields(self):
    variant = vcfio.Variant(
        reference_name='chr19', start=11, end=12, reference_bases='C',
        alternate_bases=['A', 'TT'], names=['rs1', 'rs2'], quality=2,
        filters=['PASS'],
        info={'IFR': [0.1, 0.2],
              'IFR2': [0.2, 0.3],
              'IS': 'some data',
              'ISR': ['data1', 'data2']},
        calls=[
            vcfio.VariantCall(
                name='Sample1', genotype=[0, 1], phaseset='*',
                info={'GQ': 20, 'FIR': [10, 20]}),
            vcfio.VariantCall(
                name='Sample2', genotype=[1, 0],
                info={'GQ': 10, 'FB': True}),
            vcfio.VariantCall(
                name='Sample3', genotype=[vcfio.MISSING_GENOTYPE_VALUE])])
    header_num_dict = {'IFR': 'A', 'IFR2': 'A', 'IS': '1', 'ISR': '2'}
    expected_row = {
        ColumnKeyConstants.REFERENCE_NAME: 'chr19',
        ColumnKeyConstants.START_POSITION: 11,
        ColumnKeyConstants.END_POSITION: 12,
        ColumnKeyConstants.REFERENCE_BASES: 'C',
        ColumnKeyConstants.ALTERNATE_BASES: [
            {ColumnKeyConstants.ALTERNATE_BASES_ALT: 'A',
             'IFR': 0.1, 'IFR2': 0.2},
            {ColumnKeyConstants.ALTERNATE_BASES_ALT: 'TT',
             'IFR': 0.2, 'IFR2': 0.3}],
        ColumnKeyConstants.NAMES: ['rs1', 'rs2'],
        ColumnKeyConstants.QUALITY: 2,
        ColumnKeyConstants.FILTER: ['PASS'],
        ColumnKeyConstants.CALLS: [
            {ColumnKeyConstants.CALLS_NAME: 'Sample1',
             ColumnKeyConstants.CALLS_GENOTYPE: [0, 1],
             ColumnKeyConstants.CALLS_PHASESET: '*',
             'GQ': 20, 'FIR': [10, 20]},
            {ColumnKeyConstants.CALLS_NAME: 'Sample2',
             ColumnKeyConstants.CALLS_GENOTYPE: [1, 0],
             ColumnKeyConstants.CALLS_PHASESET: None,
             'GQ': 10, 'FB': True},
            {ColumnKeyConstants.CALLS_NAME: 'Sample3',
             ColumnKeyConstants.CALLS_GENOTYPE: [vcfio.MISSING_GENOTYPE_VALUE],
             ColumnKeyConstants.CALLS_PHASESET: None}],
        'IS': 'some data',
        'ISR': ['data1', 'data2']}
    proc_variant = _get_processed_variant(variant, header_num_dict)
    self.assertEqual([expected_row],
                     list(self._row_generator.get_rows(proc_variant)))

  def test_no_alternate_bases(self):
    variant = vcfio.Variant(
        reference_name='chr19', start=11, end=12, reference_bases='CT',
        alternate_bases=[], filters=['q10'],
        info={'IS': 'some data',
              'ISR': ['data1', 'data2']})
    header_num_dict = {'IS': '1', 'ISR': '2'}
    proc_variant = _get_processed_variant(variant, header_num_dict)
    expected_row = {
        ColumnKeyConstants.REFERENCE_NAME: 'chr19',
        ColumnKeyConstants.START_POSITION: 11,
        ColumnKeyConstants.END_POSITION: 12,
        ColumnKeyConstants.REFERENCE_BASES: 'CT',
        ColumnKeyConstants.ALTERNATE_BASES: [],
        ColumnKeyConstants.FILTER: ['q10'],
        ColumnKeyConstants.CALLS: [],
        'IS': 'some data',
        'ISR': ['data1', 'data2']}

    self.assertEqual([expected_row],
                     list(self._row_generator.get_rows(proc_variant)))

  def test_some_fields_set(self):
    variant = vcfio.Variant(
        reference_name='chr19', start=None, end=123, reference_bases=None,
        alternate_bases=[], quality=20)
    proc_variant = _get_processed_variant(variant)
    expected_row = {
        ColumnKeyConstants.REFERENCE_NAME: 'chr19',
        ColumnKeyConstants.START_POSITION: None,
        ColumnKeyConstants.END_POSITION: 123,
        ColumnKeyConstants.REFERENCE_BASES: None,
        ColumnKeyConstants.ALTERNATE_BASES: [],
        ColumnKeyConstants.QUALITY: 20,
        ColumnKeyConstants.CALLS: []}

    self.assertEqual([expected_row],
                     list(self._row_generator.get_rows(proc_variant)))

  def test_no_field_set(self):
    variant = vcfio.Variant()
    proc_variant = _get_processed_variant(variant)
    expected_row = {
        ColumnKeyConstants.REFERENCE_NAME: None,
        ColumnKeyConstants.START_POSITION: None,
        ColumnKeyConstants.END_POSITION: None,
        ColumnKeyConstants.REFERENCE_BASES: None,
        ColumnKeyConstants.ALTERNATE_BASES: [],
        ColumnKeyConstants.CALLS: []}
    self.assertEqual([expected_row],
                     list(self._row_generator.get_rows(proc_variant)))

  def test_null_repeated_fields(self):
    variant = vcfio.Variant(
        reference_name='chr19', start=11, end=12, reference_bases='CT',
        alternate_bases=[], filters=['q10'],
        info={'IIR': [0, 1, None],
              'IBR': [True, None, False],
              'IFR': [0.1, 0.2, None, 0.4],
              'ISR': [None, 'data1', 'data2']})
    header_num_dict = {'IIR': '3', 'IBR': '3', 'IFR': '4', 'ISR': '3'}
    proc_variant = _get_processed_variant(variant, header_num_dict)
    expected_row = {
        ColumnKeyConstants.REFERENCE_NAME: 'chr19',
        ColumnKeyConstants.START_POSITION: 11,
        ColumnKeyConstants.END_POSITION: 12,
        ColumnKeyConstants.REFERENCE_BASES: 'CT',
        ColumnKeyConstants.ALTERNATE_BASES: [],
        ColumnKeyConstants.FILTER: ['q10'],
        ColumnKeyConstants.CALLS: [],
        'IIR': [0,
                1,
                bigquery_sanitizer._DEFAULT_NULL_NUMERIC_VALUE_REPLACEMENT],
        'IBR': [True, False, False],
        'IFR': [0.1,
                0.2,
                bigquery_sanitizer._DEFAULT_NULL_NUMERIC_VALUE_REPLACEMENT,
                0.4],
        'ISR': ['.', 'data1', 'data2']}
    self.assertEqual([expected_row],
                     list(self._row_generator.get_rows(proc_variant)))

  def test_unicode_fields(self):
    sample_unicode_str = u'\xc3\xb6'
    sample_utf8_str = sample_unicode_str.encode('utf-8')
    variant = vcfio.Variant(
        reference_name='chr19', start=11, end=12, reference_bases='CT',
        alternate_bases=[], filters=[sample_unicode_str, sample_utf8_str],
        info={'IS': sample_utf8_str,
              'ISR': [sample_unicode_str, sample_utf8_str]})
    header_num_dict = {'IS': '1', 'ISR': '2'}
    proc_variant = _get_processed_variant(variant, header_num_dict)
    expected_row = {
        ColumnKeyConstants.REFERENCE_NAME: 'chr19',
        ColumnKeyConstants.START_POSITION: 11,
        ColumnKeyConstants.END_POSITION: 12,
        ColumnKeyConstants.REFERENCE_BASES: 'CT',
        ColumnKeyConstants.ALTERNATE_BASES: [],
        ColumnKeyConstants.FILTER: [sample_unicode_str, sample_unicode_str],
        ColumnKeyConstants.CALLS: [],
        'IS': sample_unicode_str,
        'ISR': [sample_unicode_str, sample_unicode_str]}
    self.assertEqual([expected_row],
                     list(self._row_generator.get_rows(proc_variant)))

  def test_nonstandard_float_values(self):
    variant = vcfio.Variant(
        reference_name='chr19', start=11, end=12, reference_bases='CT',
        alternate_bases=['A', 'C', 'T', 'TC'], filters=[],
        calls=[vcfio.VariantCall(name='Sample1', genotype=[0, 1], phaseset='*',
                                 info={'GQ': float('inf')})],
        info={'IF': float('inf'),
              'IFR': [float('-inf'), float('nan'), 1.2],
              'IF2': float('nan'),
              'IF3': [float('-inf'), float('nan'), float('inf'), 1.2]},
    )
    header_num_dict = {'IF': '1', 'IFR': '3', 'IF2': '1', 'IF3': 'A'}
    proc_variant = _get_processed_variant(variant, header_num_dict)
    expected_row = {
        ColumnKeyConstants.REFERENCE_NAME: 'chr19',
        ColumnKeyConstants.START_POSITION: 11,
        ColumnKeyConstants.END_POSITION: 12,
        ColumnKeyConstants.REFERENCE_BASES: 'CT',
        ColumnKeyConstants.ALTERNATE_BASES: [
            {'IF3': -bigquery_sanitizer._INF_FLOAT_VALUE, 'alt': 'A'},
            {'IF3': None, 'alt': 'C'},
            {'IF3': bigquery_sanitizer._INF_FLOAT_VALUE, 'alt': 'T'},
            {'IF3': 1.2, 'alt': 'TC'}
        ],
        ColumnKeyConstants.CALLS: [
            {
                ColumnKeyConstants.CALLS_NAME: 'Sample1',
                ColumnKeyConstants.CALLS_GENOTYPE: [0, 1],
                ColumnKeyConstants.CALLS_PHASESET: '*',
                'GQ': bigquery_sanitizer._INF_FLOAT_VALUE
            }
        ],
        'IF': bigquery_sanitizer._INF_FLOAT_VALUE,
        'IFR': [-bigquery_sanitizer._INF_FLOAT_VALUE,
                bigquery_sanitizer._DEFAULT_NULL_NUMERIC_VALUE_REPLACEMENT,
                1.2],
        'IF2': None
    }
    self.assertEqual([expected_row],
                     list(self._row_generator.get_rows(proc_variant)))

  def test_nonstandard_fields_names(self):
    variant = vcfio.Variant(
        reference_name='chr19', start=11, end=12, reference_bases='CT',
        alternate_bases=[],
        info={'IS': 'data1',
              '_IS': 'data2'})
    header_num_dict = {'IS': '1', '_IS': '2'}
    proc_variant = _get_processed_variant(variant, header_num_dict)
    expected_row = {
        ColumnKeyConstants.REFERENCE_NAME: 'chr19',
        ColumnKeyConstants.START_POSITION: 11,
        ColumnKeyConstants.END_POSITION: 12,
        ColumnKeyConstants.REFERENCE_BASES: 'CT',
        ColumnKeyConstants.ALTERNATE_BASES: [],
        ColumnKeyConstants.CALLS: [],
        'IS': 'data1',
        'field__IS': 'data2'}
    self.assertEqual([expected_row],
                     list(self._row_generator.get_rows(proc_variant)))

  def test_sharded_rows(self):
    """Tests splitting BigQuery rows that are larger than BigQuery limit."""
    num_calls = 10  # Number of calls for a variant in this test.
    num_first_row_calls = 6  # BigQuery row limit is adjusted accordingly.
    variant = vcfio.Variant(
        reference_name='chr19', start=11, end=12, reference_bases='C',
        alternate_bases=['A', 'TT'], names=['rs1', 'rs2'], quality=2,
        filters=['PASS'],
        info={'IFR': [0.1, 0.2],
              'IFR2': [0.2, 0.3],
              'IS': 'some data'},
        calls=[
            vcfio.VariantCall(
                name='Sample{}'.format(i), genotype=[0, 1], phaseset='*',
                info={'GQ': 20, 'FIR': [10, 20]})
            for i in range(num_calls)])
    header_num_dict = {'IFR': 'A', 'IFR2': 'A', 'IS': '1'}
    proc_variant = _get_processed_variant(variant, header_num_dict)

    expected_rows = [
        {
            ColumnKeyConstants.REFERENCE_NAME: 'chr19',
            ColumnKeyConstants.START_POSITION: 11,
            ColumnKeyConstants.END_POSITION: 12,
            ColumnKeyConstants.REFERENCE_BASES: 'C',
            ColumnKeyConstants.ALTERNATE_BASES: [
                {ColumnKeyConstants.ALTERNATE_BASES_ALT: 'A',
                 'IFR': 0.1, 'IFR2': 0.2},
                {ColumnKeyConstants.ALTERNATE_BASES_ALT: 'TT',
                 'IFR': 0.2, 'IFR2': 0.3}],
            ColumnKeyConstants.NAMES: ['rs1', 'rs2'],
            ColumnKeyConstants.QUALITY: 2,
            ColumnKeyConstants.FILTER: ['PASS'],
            ColumnKeyConstants.CALLS: [
                {ColumnKeyConstants.CALLS_NAME: 'Sample{}'.format(i),
                 ColumnKeyConstants.CALLS_GENOTYPE: [0, 1],
                 ColumnKeyConstants.CALLS_PHASESET: '*',
                 'GQ': 20, 'FIR': [10, 20]}
                for i in range(num_first_row_calls)],
            'IS': 'some data'
        },
        {
            ColumnKeyConstants.REFERENCE_NAME: 'chr19',
            ColumnKeyConstants.START_POSITION: 11,
            ColumnKeyConstants.END_POSITION: 12,
            ColumnKeyConstants.REFERENCE_BASES: 'C',
            ColumnKeyConstants.ALTERNATE_BASES: [
                {ColumnKeyConstants.ALTERNATE_BASES_ALT: 'A',
                 'IFR': 0.1, 'IFR2': 0.2},
                {ColumnKeyConstants.ALTERNATE_BASES_ALT: 'TT',
                 'IFR': 0.2, 'IFR2': 0.3}],
            ColumnKeyConstants.NAMES: ['rs1', 'rs2'],
            ColumnKeyConstants.QUALITY: 2,
            ColumnKeyConstants.FILTER: ['PASS'],
            ColumnKeyConstants.CALLS: [
                {ColumnKeyConstants.CALLS_NAME: 'Sample{}'.format(i),
                 ColumnKeyConstants.CALLS_GENOTYPE: [0, 1],
                 ColumnKeyConstants.CALLS_PHASESET: '*',
                 'GQ': 20, 'FIR': [10, 20]}
                for i in range(num_first_row_calls, num_calls)],
            'IS': 'some data'
        },
    ]
    with mock.patch.object(bigquery_vcf_data_converter,
                           '_MAX_BIGQUERY_ROW_SIZE_BYTES',
                           num_first_row_calls * len(json.dumps(
                               expected_rows[0][ColumnKeyConstants.CALLS][0]))):
      with mock.patch.object(bigquery_vcf_data_converter,
                             '_MIN_NUM_CALLS_FOR_ROW_SIZE_ESTIMATION',
                             num_calls):
        self.assertEqual(expected_rows,
                         list(self._row_generator.get_rows(proc_variant)))

  def test_omit_empty_sample_calls(self):
    variant = vcfio.Variant(
        reference_name='chr19', start=11, end=12, reference_bases='C',
        alternate_bases=[], names=['rs1', 'rs2'], quality=2,
        filters=['PASS'],
        info={},
        calls=[
            vcfio.VariantCall(
                name='Sample1', info={'GQ': None}),
            vcfio.VariantCall(
                name='Sample2', genotype=[1, 0],
                info={'GQ': 10}),
            vcfio.VariantCall(
                name='Sample3', genotype=[vcfio.MISSING_GENOTYPE_VALUE,
                                          vcfio.MISSING_GENOTYPE_VALUE])])
    proc_variant = _get_processed_variant(variant)
    expected_row = {
        ColumnKeyConstants.REFERENCE_NAME: 'chr19',
        ColumnKeyConstants.START_POSITION: 11,
        ColumnKeyConstants.END_POSITION: 12,
        ColumnKeyConstants.REFERENCE_BASES: 'C',
        ColumnKeyConstants.ALTERNATE_BASES: [],
        ColumnKeyConstants.NAMES: ['rs1', 'rs2'],
        ColumnKeyConstants.QUALITY: 2,
        ColumnKeyConstants.FILTER: ['PASS'],
        ColumnKeyConstants.CALLS: [
            {ColumnKeyConstants.CALLS_NAME: 'Sample2',
             ColumnKeyConstants.CALLS_GENOTYPE: [1, 0],
             ColumnKeyConstants.CALLS_PHASESET: None,
             'GQ': 10}]}

    self.assertEqual(
        [expected_row],
        list(self._row_generator.get_rows(proc_variant,
                                          omit_empty_sample_calls=True)))

  def test_schema_conflict_in_info_field_type(self):
    variant = vcfio.Variant(
        reference_name='chr19', start=11, end=12, reference_bases='CT',
        alternate_bases=[], filters=[],
        info={'IB': 1,
              'II': 1.1,
              'IFR': [1, 2],
              'ISR': [1.0, 2.0]})
    header_num_dict = {'IB': '1', 'II': '1', 'IFR': '2', 'ISR': '2'}
    proc_variant = _get_processed_variant(variant, header_num_dict)
    expected_row = {
        ColumnKeyConstants.REFERENCE_NAME: 'chr19',
        ColumnKeyConstants.START_POSITION: 11,
        ColumnKeyConstants.END_POSITION: 12,
        ColumnKeyConstants.REFERENCE_BASES: 'CT',
        ColumnKeyConstants.ALTERNATE_BASES: [],
        ColumnKeyConstants.CALLS: [],
        'IB': True,
        'II': 1,
        'IFR': [1.0, 2.0],
        'ISR': ['1.0', '2.0']}
    self.assertEqual([expected_row],
                     list(self._row_generator.get_rows(
                         proc_variant, allow_incompatible_records=True)))

    with self.assertRaises(ValueError):
      variant = vcfio.Variant(
          reference_name='chr19', start=11, end=12, reference_bases='CT',
          alternate_bases=[], filters=[],
          # String cannot be casted to integer.
          info={'II': '1.1'})
      header_num_dict = {'II': '1'}
      # self._get_row_list_from_variant(
      #     variant, header_num_dict, allow_incompatible_records=True)
      proc_variant = _get_processed_variant(variant, header_num_dict)
      list(self._row_generator.get_rows(proc_variant,
                                        allow_incompatible_records=True))
      self.fail('String data for an integer schema must cause an exception')

  def test_schema_conflict_in_info_field_number(self):
    variant = vcfio.Variant(
        reference_name='chr19', start=11, end=12, reference_bases='CT',
        alternate_bases=[], filters=[],
        info={'IB': [1, 2],
              'IBR': 1,
              'II': [10, 20],
              'IFR': 1.1,
              'ISR': 'foo'},)
    header_num_dict = {'IB': '2', 'IBR': '1', 'II': '2', 'IFR': '1', 'ISR': '1'}
    proc_variant = _get_processed_variant(variant, header_num_dict)
    expected_row = {
        ColumnKeyConstants.REFERENCE_NAME: 'chr19',
        ColumnKeyConstants.START_POSITION: 11,
        ColumnKeyConstants.END_POSITION: 12,
        ColumnKeyConstants.REFERENCE_BASES: 'CT',
        ColumnKeyConstants.ALTERNATE_BASES: [],
        ColumnKeyConstants.CALLS: [],
        'IB': True,
        'IBR': [True],
        'II': 10,
        'IFR': [1.1],
        'ISR': ['foo']
    }

    self.assertEqual(
        [expected_row],
        list(self._row_generator.get_rows(proc_variant,
                                          allow_incompatible_records=True)))

  def test_schema_conflict_in_format_field_type(self):
    variant = vcfio.Variant(
        reference_name='chr19', start=11, end=12, reference_bases='CT',
        alternate_bases=[], filters=[],
        calls=[
            vcfio.VariantCall(
                name='Sample1', genotype=[0, 1], phaseset='*',
                info={'FB': '', 'FI': 1.0, 'FSR': [1, 2]}),
            vcfio.VariantCall(
                name='Sample2', genotype=[1, 0],
                info={'FB': 1, 'FI': True, 'FSR': [1.0, 2.0]})])
    proc_variant = _get_processed_variant(variant)
    expected_row = {
        ColumnKeyConstants.REFERENCE_NAME: 'chr19',
        ColumnKeyConstants.START_POSITION: 11,
        ColumnKeyConstants.END_POSITION: 12,
        ColumnKeyConstants.REFERENCE_BASES: 'CT',
        ColumnKeyConstants.ALTERNATE_BASES: [],
        ColumnKeyConstants.CALLS: [
            {ColumnKeyConstants.CALLS_NAME: 'Sample1',
             ColumnKeyConstants.CALLS_GENOTYPE: [0, 1],
             ColumnKeyConstants.CALLS_PHASESET: '*',
             'FB': False, 'FI': 1, 'FSR': ['1', '2']},
            {ColumnKeyConstants.CALLS_NAME: 'Sample2',
             ColumnKeyConstants.CALLS_GENOTYPE: [1, 0],
             ColumnKeyConstants.CALLS_PHASESET: None,
             'FB': True, 'FI': 1, 'FSR': ['1.0', '2.0']},],
    }

    self.assertEqual(
        [expected_row],
        list(self._row_generator.get_rows(proc_variant,
                                          allow_incompatible_records=True)))

    with self.assertRaises(ValueError):
      variant = vcfio.Variant(
          reference_name='chr19', start=11, end=12, reference_bases='CT',
          alternate_bases=[], filters=[],
          # String cannot be casted to integer.
          calls=[
              vcfio.VariantCall(
                  name='Sample1', genotype=[0, 1], phaseset='*',
                  info={'FI': 'string_for_int_field'}),],)
      proc_variant = _get_processed_variant(variant)
      list(self._row_generator.get_rows(proc_variant,
                                        allow_incompatible_records=True))
      self.fail('String data for an integer schema must cause an exception')

  def test_schema_conflict_in_format_field_number(self):
    variant = vcfio.Variant(
        reference_name='chr19', start=11, end=12, reference_bases='CT',
        alternate_bases=[], filters=[],
        calls=[
            vcfio.VariantCall(
                name='Sample1', genotype=[0, 1], phaseset='*',
                info={'FB': [1, 2], 'FI': [1, 2], 'FSR': 'str'}),
            vcfio.VariantCall(
                name='Sample2', genotype=[1, 0],
                info={'FB': [], 'FI': [], 'FSR': ''})])
    proc_variant = _get_processed_variant(variant)
    expected_row = {
        ColumnKeyConstants.REFERENCE_NAME: 'chr19',
        ColumnKeyConstants.START_POSITION: 11,
        ColumnKeyConstants.END_POSITION: 12,
        ColumnKeyConstants.REFERENCE_BASES: 'CT',
        ColumnKeyConstants.ALTERNATE_BASES: [],
        ColumnKeyConstants.CALLS: [
            {ColumnKeyConstants.CALLS_NAME: 'Sample1',
             ColumnKeyConstants.CALLS_GENOTYPE: [0, 1],
             ColumnKeyConstants.CALLS_PHASESET: '*',
             'FB': True, 'FI': 1, 'FSR': ['str']},
            {ColumnKeyConstants.CALLS_NAME: 'Sample2',
             ColumnKeyConstants.CALLS_GENOTYPE: [1, 0],
             ColumnKeyConstants.CALLS_PHASESET: None,
             'FB': False, 'FI': None, 'FSR': ['']},],
    }

    self.assertEqual(
        [expected_row],
        list(self._row_generator.get_rows(proc_variant,
                                          allow_incompatible_records=True)))


class VariantGeneratorTest(unittest.TestCase):
  """Test cases for `VariantGenerator` class."""

  def setUp(self):
    self._variant_generator = bigquery_vcf_data_converter.VariantGenerator()

  def test_alternate_bases(self):
    alternate_base_records = _get_big_query_row()[
        ColumnKeyConstants.ALTERNATE_BASES]

    expected_alternate_bases = ['A', 'TT']

    self.assertEqual(
        expected_alternate_bases,
        self._variant_generator._get_alternate_bases(alternate_base_records))

  def test_get_variant_info(self):
    row = _get_big_query_row()
    expected_variant_info = {'IFR': [1, 0.2],
                             'IFR2': [0.2, 0.3],
                             'IS': 'some data',
                             'ISR': ['data1', 'data2']}

    self.assertEqual(expected_variant_info,
                     self._variant_generator._get_variant_info(row))

  def test_get_variant_info_annotation(self):
    variant_generator = bigquery_vcf_data_converter.VariantGenerator({
        'CSQ': ['allele', 'Consequence', 'AF', 'IMPACT']
    })
    row = {
        unicode(ColumnKeyConstants.ALTERNATE_BASES): [
            {
                unicode(ColumnKeyConstants.ALTERNATE_BASES_ALT): u'G',
                unicode('CSQ'): [
                    {u'allele': 'G',
                     u'Consequence': u'upstream_gene_variant',
                     u'AF': u'',
                     u'IMPACT': u'MODIFIER'},
                    {u'allele': 'G',
                     u'Consequence': u'upstream_gene_variant',
                     u'AF': u'0.1',
                     u'IMPACT': u''}]
            },
            {
                unicode(ColumnKeyConstants.ALTERNATE_BASES_ALT): u'T',
                unicode('CSQ'): [
                    {u'allele': 'T',
                     u'Consequence': u'',
                     u'AF': u'',
                     u'IMPACT': u'MODIFIER'},
                    {u'allele': 'T',
                     u'Consequence': u'upstream_gene_variant',
                     u'AF': u'0.6',
                     u'IMPACT': u''}]

            },
            {
                unicode(ColumnKeyConstants.ALTERNATE_BASES_ALT): u'TT',
                unicode('CSQ'): []
            }
        ]
    }

    expected_variant_info = {
        'CSQ': [
            'G|upstream_gene_variant||MODIFIER',
            'G|upstream_gene_variant|0.1|',
            'T|||MODIFIER',
            'T|upstream_gene_variant|0.6|']
    }
    self.assertEqual(expected_variant_info,
                     variant_generator._get_variant_info(row))

  def test_get_variant_calls(self):
    variant_call_records = _get_big_query_row()[ColumnKeyConstants.CALLS]

    expected_calls = [
        vcfio.VariantCall(
            name='Sample1', genotype=[0, 1], phaseset='*',
            info={'GQ': 20, 'FIR': [10, 20]}),
        vcfio.VariantCall(
            name='Sample2', genotype=[1, 0],
            info={'GQ': 10, 'FB': True}),
    ]

    self.assertEqual(
        expected_calls,
        self._variant_generator._get_variant_calls(variant_call_records))

  def test_convert_bq_row_to_variant(self):
    row = _get_big_query_row()
    expected_variant = vcfio.Variant(
        reference_name='chr19', start=11, end=12, reference_bases='C',
        alternate_bases=['A', 'TT'], names=['rs1', 'rs2'], quality=2,
        filters=['PASS'],
        info={'IFR': [1, 0.2], 'IFR2': [0.2, 0.3],
              'IS': 'some data', 'ISR': ['data1', 'data2']},
        calls=[
            vcfio.VariantCall(
                name='Sample1', genotype=[0, 1], phaseset='*',
                info={'GQ': 20, 'FIR': [10, 20]}),
            vcfio.VariantCall(
                name='Sample2', genotype=[1, 0],
                info={'GQ': 10, 'FB': True})
        ]
    )

    self.assertEqual(expected_variant,
                     self._variant_generator.convert_bq_row_to_variant(row))


class ConverterCombinationTest(unittest.TestCase):
  """Test cases for combining the BigQuery VCF data converters."""

  def setUp(self):
    self._variant_generator = bigquery_vcf_data_converter.VariantGenerator()
    self._schema_descriptor = bigquery_schema_descriptor.SchemaDescriptor(
        _get_table_schema())
    self._conflict_resolver = (
        vcf_field_conflict_resolver.FieldConflictResolver())
    self._row_generator = bigquery_vcf_data_converter.BigQueryRowGenerator(
        self._schema_descriptor, self._conflict_resolver)

  def test_bq_row_to_variant_to_bq_row(self):
    row = _get_big_query_row()
    header_num_dict = {'IFR': 'A', 'IFR2': 'A', 'IS': '1', 'ISR': '2'}
    variant = self._variant_generator.convert_bq_row_to_variant(row)
    proc_variant = _get_processed_variant(variant, header_num_dict)
    converted_row = list(self._row_generator.get_rows(proc_variant))
    self.assertEqual([row], converted_row)

  def test_variant_to_bq_row_to_variant(self):
    variant = vcfio.Variant(
        reference_name='chr19', start=11, end=12, reference_bases='C',
        alternate_bases=['A', 'TT'], names=['rs1', 'rs2'], quality=2,
        filters=['PASS'],
        info={'IFR': [0.1, 0.2],
              'IFR2': [0.2, 0.3],
              'IS': 'some data',
              'ISR': ['data1', 'data2']},
        calls=[
            vcfio.VariantCall(
                name='Sample1', genotype=[0, 1], phaseset='*',
                info={'GQ': 20, 'FIR': [10, 20]}),
            vcfio.VariantCall(
                name='Sample2', genotype=[1, 0],
                info={'GQ': 10, 'FB': True}),
            vcfio.VariantCall(
                name='Sample3', genotype=[vcfio.MISSING_GENOTYPE_VALUE])])
    header_num_dict = {'IFR': 'A', 'IFR2': 'A', 'IS': '1', 'ISR': '2'}

    proc_variant = _get_processed_variant(variant, header_num_dict)
    row = list(self._row_generator.get_rows(proc_variant))
    converted_variant = self._variant_generator.convert_bq_row_to_variant(
        row[0])
    self.assertEqual(variant, converted_variant)
