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

"""Tests for infer_headers module."""

from __future__ import absolute_import

from collections import OrderedDict
import unittest

from apache_beam import pvalue
from apache_beam.testing.test_pipeline import TestPipeline
from apache_beam.testing.util import assert_that
from apache_beam.testing.util import equal_to
from apache_beam.transforms import Create
from vcf.parser import _Format as Format
from vcf.parser import _Info as Info
from vcf.parser import field_counts

from gcp_variant_transforms.beam_io import vcf_header_io
from gcp_variant_transforms.beam_io import vcfio
from gcp_variant_transforms.testing import asserts
from gcp_variant_transforms.transforms import infer_headers


class InferHeaderFieldsTest(unittest.TestCase):
  """Test case for `InferHeaderFields` DoFn."""

  def _get_sample_header_fields(self, with_annotation=False):
    """Provides a simple `VcfHeader` with info and format fields

    Args:
      with_annotation: Can be bool or list of tuples. Tuples should be
        additional annotation fields in the format (key, `Info`).
    """
    infos = OrderedDict([
        ('IS', Info('I1', 1, 'String', 'desc', 'src', 'v')),
        ('ISI', Info('ISI', 1, 'Int', 'desc', 'src', 'v')),
        ('ISF', Info('ISF', 1, 'Float', 'desc', 'src', 'v')),
        ('IF', Info('IF', 1, 'Float', 'desc', 'src', 'v')),
        ('IB', Info('I1', 1, 'Flag', 'desc', 'src', 'v')),
        ('IA', Info('IA', field_counts['A'], 'Integer', 'desc', 'src', 'v'))])
    if with_annotation:
      infos['CSQ'] = Info(
          'CSQ',
          field_counts['.'],
          'String',
          'Annotations from VEP. Format: Allele|Gene|Position|Score',
          'src',
          'v')
      if isinstance(with_annotation, list):
        for key, value in with_annotation:
          infos[key] = value
    formats = OrderedDict([
        ('FS', Format('FS', 1, 'String', 'desc')),
        ('FI', Format('FI', 2, 'Integer', 'desc')),
        ('FU', Format('FU', field_counts['.'], 'Float', 'desc')),
        ('GT', Format('GT', 2, 'Integer', 'Special GT key')),
        ('PS', Format('PS', 1, 'Integer', 'Special PS key'))])
    return vcf_header_io.VcfHeader(infos=infos, formats=formats)

  def _get_sample_variant_1(self):
    variant = vcfio.Variant(
        reference_name='chr19', start=11, end=12, reference_bases='C',
        alternate_bases=['A', 'TT'], names=['rs1', 'rs2'], quality=2,
        filters=['PASS'],
        info={'IS': 'some data', 'ISI': '1', 'ISF': '1.0',
              'IF': 1.0, 'IB': True, 'IA': [1, 2]},
        calls=[vcfio.VariantCall(
            name='Sample1', genotype=[0, 1], phaseset='*',
            info={'FI': 20, 'FU': [10.0, 20.0]})]
    )
    return variant

  def _get_sample_variant_2(self):
    variant = vcfio.Variant(
        reference_name='20', start=123, end=125, reference_bases='CT',
        alternate_bases=[], filters=['q10', 's10'],
        info={'IS_2': 'some data'},
        calls=[vcfio.VariantCall(
            name='Sample1', genotype=[0, 1], phaseset='*', info={'FI_2': 20})]
    )
    return variant

  def _get_sample_variant_info_ia_cardinality_mismatch(self):
    variant = vcfio.Variant(
        reference_name='chr19', start=11, end=12, reference_bases='C',
        alternate_bases=['A', 'TT'], names=['rs1', 'rs2'], quality=2,
        filters=['PASS'],
        info={'IS': 'some data',
              'ISI': '1',
              'ISF': '1.0',
              'IF': 1.0,
              'IB': True,
              'IA': [0.1]},
        calls=[vcfio.VariantCall(
            name='Sample1', genotype=[0, 1], phaseset='*',
            info={'FI': 20, 'FU': [10.0, 20.0]})]
    )
    return variant

  def _get_sample_variant_info_ia_float_in_list(self):
    variant = vcfio.Variant(
        reference_name='chr19', start=11, end=12, reference_bases='C',
        alternate_bases=['A', 'TT'], names=['rs1', 'rs2'], quality=2,
        filters=['PASS'],
        info={'IS': 'some data',
              'ISI': '1',
              'ISF': '1.0',
              'IF': 1.0,
              'IB': True,
              'IA': [1, 0.2]},
        calls=[vcfio.VariantCall(
            name='Sample1', genotype=[0, 1], phaseset='*',
            info={'FI': 20, 'FU': [10.0, 20.0]})]
    )
    return variant

  def _get_sample_variant_info_ia_float_2_0_in_list(self):
    variant = vcfio.Variant(
        reference_name='chr19', start=11, end=12, reference_bases='C',
        alternate_bases=['A', 'TT'], names=['rs1', 'rs2'], quality=2,
        filters=['PASS'],
        info={'IS': 'some data',
              'ISI': '1',
              'ISF': '1.0',
              'IF': 1.0,
              'IB': True,
              'IA': [1, 2.0]},
        calls=[vcfio.VariantCall(
            name='Sample1', genotype=[0, 1], phaseset='*',
            info={'FI': 20, 'FU': [10.0, 20.0]})]
    )
    return variant

  def _get_sample_variant_format_fi_float_value(self):
    variant = vcfio.Variant(
        reference_name='chr19', start=11, end=12, reference_bases='C',
        alternate_bases=['A', 'TT'], names=['rs1', 'rs2'], quality=2,
        filters=['PASS'],
        info={'IS': 'some data',
              'ISI': '1',
              'ISF': '1.0',
              'IF': 1.0,
              'IB': True,
              'IA': [0.1, 0.2]},
        calls=[vcfio.VariantCall(
            name='Sample1', genotype=[0, 1], phaseset='*',
            info={'FI': 20.1, 'FU': [10.0, 20.0]})]
    )
    return variant

  def test_header_fields_inferred_one_variant(self):
    with TestPipeline() as p:
      variant = self._get_sample_variant_1()
      inferred_headers = (
          p
          | Create([variant])
          | 'InferHeaderFields' >>
          infer_headers.InferHeaderFields(defined_headers=None,
                                          infer_headers=True))

      expected_infos = {'IS': Info('IS', 1, 'String', '', '', ''),
                        'ISI': Info('ISI', 1, 'Integer', '', '', ''),
                        'ISF': Info('ISF', 1, 'Float', '', '', ''),
                        'IF': Info('IF', 1, 'Float', '', '', ''),
                        'IB': Info('IB', 0, 'Flag', '', '', ''),
                        'IA': Info('IA', None, 'Integer', '', '', '')}
      expected_formats = {'FI': Format('FI', 1, 'Integer', ''),
                          'FU': Format('FU', None, 'Float', '')}

      expected = vcf_header_io.VcfHeader(
          infos=expected_infos, formats=expected_formats)
      assert_that(inferred_headers, equal_to([expected]))
      p.run()

  def test_defined_fields_filtered_one_variant(self):
    # All FORMATs and INFOs are already defined in the header section of VCF
    # files.
    with TestPipeline() as p:
      vcf_headers = self._get_sample_header_fields()
      vcf_headers_side_input = p | 'vcf_headers' >> Create([vcf_headers])
      variant = self._get_sample_variant_1()
      inferred_headers = (
          p
          | Create([variant])
          | 'InferHeaderFields' >>
          infer_headers.InferHeaderFields(
              pvalue.AsSingleton(vcf_headers_side_input),
              infer_headers=True))
      expected = vcf_header_io.VcfHeader()
      assert_that(inferred_headers, equal_to([expected]))
      p.run()

  def test_header_fields_inferred_from_two_variants(self):
    with TestPipeline() as p:
      variant_1 = self._get_sample_variant_1()
      variant_2 = self._get_sample_variant_2()
      inferred_headers = (
          p
          | Create([variant_1, variant_2])
          | 'InferHeaderFields' >>
          infer_headers.InferHeaderFields(defined_headers=None,
                                          infer_headers=True))

      expected_infos = {'IS': Info('IS', 1, 'String', '', '', ''),
                        'ISI': Info('ISI', 1, 'Integer', '', '', ''),
                        'ISF': Info('ISF', 1, 'Float', '', '', ''),
                        'IF': Info('IF', 1, 'Float', '', '', ''),
                        'IB': Info('IB', 0, 'Flag', '', '', ''),
                        'IA': Info('IA', None, 'Integer', '', '', ''),
                        'IS_2': Info('IS_2', 1, 'String', '', '', '')}
      expected_formats = {'FI': Format('FI', 1, 'Integer', ''),
                          'FU': Format('FU', None, 'Float', ''),
                          'FI_2': Format('FI_2', 1, 'Integer', '')}

      expected = vcf_header_io.VcfHeader(
          infos=expected_infos, formats=expected_formats)
      assert_that(inferred_headers,
                  asserts.header_fields_equal_ignore_order([expected]))
      p.run()

  def test_defined_fields_filtered_two_variants(self):
    # Only INFO and FORMAT in the first variants are already defined in the
    # header section of the VCF files.
    with TestPipeline() as p:
      vcf_headers = self._get_sample_header_fields()
      vcf_headers_side_input = p | 'vcf_header' >> Create([vcf_headers])
      variant_1 = self._get_sample_variant_1()
      variant_2 = self._get_sample_variant_2()
      inferred_headers = (
          p
          | Create([variant_1, variant_2])
          | 'InferHeaderFields' >>
          infer_headers.InferHeaderFields(
              pvalue.AsSingleton(vcf_headers_side_input),
              infer_headers=True))

      expected_infos = {'IS_2': Info('IS_2', 1, 'String', '', '', '')}
      expected_formats = {'FI_2': Format('FI_2', 1, 'Integer', '')}
      expected = vcf_header_io.VcfHeader(
          infos=expected_infos, formats=expected_formats)
      assert_that(inferred_headers,
                  asserts.header_fields_equal_ignore_order([expected]))
      p.run()

  def test_infer_mismatched_info_field_no_mismatches(self):
    variant = self._get_sample_variant_info_ia_float_2_0_in_list()
    infos = {'IS': Info('IS', 1, 'String', '', '', ''),
             'ISI': Info('ISI', 1, 'Integer', '', '', ''),
             'ISF': Info('ISF', 1, 'Float', '', '', ''),
             'IF': Info('IF', 1, 'Float', '', '', ''),
             'IB': Info('IB', 0, 'Flag', '', '', ''),
             'IA': Info('IA', 'A', 'Integer', '', '', '')}
    infer_header_fields = infer_headers._InferHeaderFields(infer_headers=True)
    corrected_info = infer_header_fields._infer_mismatched_info_field(
        'IA', variant.info.get('IA'),
        vcf_header_io.VcfHeader(infos=infos).infos.get('IA'),
        len(variant.alternate_bases))
    self.assertEqual(None, corrected_info)

  def test_infer_mismatched_info_field_correct_num(self):
    variant = self._get_sample_variant_info_ia_cardinality_mismatch()
    infos = {'IS': Info('IS', 1, 'String', '', '', ''),
             'ISI': Info('ISI', 1, 'Integer', '', '', ''),
             'ISF': Info('ISF', 1, 'Float', '', '', ''),
             'IF': Info('IF', 1, 'Float', '', '', ''),
             'IB': Info('IB', 0, 'Flag', '', '', ''),
             'IA': Info('IA', -1, 'Float', '', '', '')}
    infer_header_fields = infer_headers._InferHeaderFields(infer_headers=True)
    corrected_info = infer_header_fields._infer_mismatched_info_field(
        'IA', variant.info.get('IA'),
        vcf_header_io.VcfHeader(infos=infos).infos.get('IA'),
        len(variant.alternate_bases))
    expected = Info('IA', None, 'Float', '', '', '')
    self.assertEqual(expected, corrected_info)

  def test_infer_mismatched_info_field_correct_type(self):
    variant = self._get_sample_variant_info_ia_cardinality_mismatch()
    infos = {'IS': Info('IS', 1, 'String', '', '', ''),
             'ISI': Info('ISI', 1, 'Integer', '', '', ''),
             'ISF': Info('ISF', 1, 'Float', '', '', ''),
             'IF': Info('IF', 1, 'Float', '', '', ''),
             'IB': Info('IB', 0, 'Flag', '', '', ''),
             'IA': Info('IA', None, 'Integer', '', '', '')}
    infer_header_fields = infer_headers._InferHeaderFields(infer_headers=True)
    corrected_info = infer_header_fields._infer_mismatched_info_field(
        'IA', variant.info.get('IA'),
        vcf_header_io.VcfHeader(infos=infos).infos.get('IA'),
        len(variant.alternate_bases)
    )
    expected = Info('IA', None, 'Float', '', '', '')
    self.assertEqual(expected, corrected_info)

  def test_infer_mismatched_info_field_correct_type_list(self):
    variant = self._get_sample_variant_info_ia_float_in_list()
    infos = {'IS': Info('IS', 1, 'String', '', '', ''),
             'ISI': Info('ISI', 1, 'Integer', '', '', ''),
             'ISF': Info('ISF', 1, 'Float', '', '', ''),
             'IF': Info('IF', 1, 'Float', '', '', ''),
             'IB': Info('IB', 0, 'Flag', '', '', ''),
             'IA': Info('IA', None, 'Integer', '', '', '')}
    infer_header_fields = infer_headers._InferHeaderFields(infer_headers=True)
    corrected_info = infer_header_fields._infer_mismatched_info_field(
        'IA', variant.info.get('IA'),
        vcf_header_io.VcfHeader(infos=infos).infos.get('IA'),
        len(variant.alternate_bases)
    )
    expected = Info('IA', None, 'Float', '', '', '')
    self.assertEqual(expected, corrected_info)

  def test_infer_info_fields_no_conflicts(self):
    variant = self._get_sample_variant_1()
    infos = {'IS': Info('IS', 1, 'String', '', '', ''),
             'ISI': Info('ISI', 1, 'Integer', '', '', ''),
             'ISF': Info('ISF', 1, 'Float', '', '', ''),
             'IF': Info('IF', 1, 'Float', '', '', ''),
             'IB': Info('IB', 0, 'Flag', '', '', ''),
             'IA': Info('IA', -1, 'Float', '', '', '')}
    infer_header_fields = infer_headers._InferHeaderFields(infer_headers=True)
    inferred_infos = infer_header_fields._infer_info_fields(
        variant, vcf_header_io.VcfHeader(infos=infos))
    self.assertEqual({}, inferred_infos)

  def test_infer_info_fields_combined_conflicts(self):
    variant = self._get_sample_variant_info_ia_cardinality_mismatch()
    infos = {'IS': Info('IS', 1, 'String', '', '', ''),
             'ISI': Info('ISI', 1, 'Integer', '', '', ''),
             'ISF': Info('ISF', 1, 'Float', '', '', ''),
             'IB': Info('IB', 0, 'Flag', '', '', ''),
             'IA': Info('IA', -1, 'Integer', '', '', '')}
    infer_header_fields = infer_headers._InferHeaderFields(infer_headers=True)
    inferred_infos = infer_header_fields._infer_info_fields(
        variant, vcf_header_io.VcfHeader(infos=infos))
    expected_infos = {'IF': Info('IF', 1, 'Float', '', '', ''),
                      'IA': Info('IA', None, 'Float', '', '', '')}
    self.assertEqual(expected_infos, inferred_infos)

  def test_infer_mismatched_format_field(self):
    variant = self._get_sample_variant_format_fi_float_value()
    formats = OrderedDict([
        ('FS', Format('FS', 1, 'String', 'desc')),
        ('FI', Format('FI', 2, 'Integer', 'desc')),
        ('FU', Format('FU', field_counts['.'], 'Float', 'desc')),
        ('GT', Format('GT', 2, 'Integer', 'Special GT key')),
        ('PS', Format('PS', 1, 'Integer', 'Special PS key'))])
    infer_header_fields = infer_headers._InferHeaderFields(infer_headers=True)
    corrected_format = infer_header_fields._infer_mismatched_format_field(
        'FI', variant.calls[0].info.get('FI'),
        vcf_header_io.VcfHeader(formats=formats).formats.get('FI'))
    expected_formats = Format('FI', 2, 'Float', 'desc')
    self.assertEqual(expected_formats, corrected_format)

  def test_infer_format_fields_no_conflicts(self):
    variant = self._get_sample_variant_1()
    formats = OrderedDict([
        ('FS', Format('FS', 1, 'String', 'desc')),
        ('FI', Format('FI', 2, 'Integer', 'desc')),
        ('FU', Format('FU', field_counts['.'], 'Float', 'desc')),
        ('GT', Format('GT', 2, 'Integer', 'Special GT key')),
        ('PS', Format('PS', 1, 'Integer', 'Special PS key'))])
    infer_header_fields = infer_headers._InferHeaderFields(infer_headers=True)
    header = infer_header_fields._infer_format_fields(
        variant, vcf_header_io.VcfHeader(formats=formats))
    self.assertEqual({}, header)

  def test_infer_format_fields_combined_conflicts(self):
    variant = self._get_sample_variant_format_fi_float_value()
    formats = OrderedDict([
        ('FS', Format('FS', 1, 'String', 'desc')),
        ('FI', Format('FI', 2, 'Integer', 'desc')),
        ('GT', Format('GT', 2, 'Integer', 'Special GT key')),
        ('PS', Format('PS', 1, 'Integer', 'Special PS key'))])
    infer_header_fields = infer_headers._InferHeaderFields(infer_headers=True)
    inferred_formats = infer_header_fields._infer_format_fields(
        variant, vcf_header_io.VcfHeader(formats=formats))
    expected_formats = {'FI': Format('FI', 2, 'Float', 'desc'),
                        'FU': Format('FU', field_counts['.'], 'Float', '')}
    self.assertEqual(expected_formats, inferred_formats)

  def test_pipeline(self):
    infos = {'IS': Info('IS', 1, 'String', '', '', ''),
             'ISI': Info('ISI', 1, 'Integer', '', '', ''),
             'ISF': Info('ISF', 1, 'Float', '', '', ''),
             'IB': Info('IB', 0, 'Flag', '', '', ''),
             'IA': Info('IA', -1, 'Integer', '', '', '')}
    formats = OrderedDict([
        ('FS', Format('FS', 1, 'String', 'desc')),
        ('FI', Format('FI', 2, 'Integer', 'desc')),
        ('GT', Format('GT', 2, 'Integer', 'Special GT key')),
        ('PS', Format('PS', 1, 'Integer', 'Special PS key'))])

    with TestPipeline() as p:
      variant_1 = self._get_sample_variant_info_ia_cardinality_mismatch()
      variant_2 = self._get_sample_variant_format_fi_float_value()
      inferred_headers = (
          p
          | Create([variant_1, variant_2])
          | 'InferHeaderFields' >>
          infer_headers.InferHeaderFields(
              defined_headers=vcf_header_io.VcfHeader(infos=infos,
                                                      formats=formats),
              allow_incompatible_records=True,
              infer_headers=True))

      expected_infos = {'IA': Info('IA', None, 'Float', '', '', ''),
                        'IF': Info('IF', 1, 'Float', '', '', '')}
      expected_formats = {'FI': Format('FI', 2, 'Float', 'desc'),
                          'FU': Format('FU', None, 'Float', '')}
      expected = vcf_header_io.VcfHeader(infos=expected_infos,
                                         formats=expected_formats)
      assert_that(inferred_headers,
                  asserts.header_fields_equal_ignore_order([expected]))
      p.run()

  def test_infer_annotation_types_no_conflicts(self):
    anno_fields = ['CSQ']
    header = self._get_sample_header_fields(with_annotation=True)
    variant = self._get_sample_variant_1()
    variant.info['CSQ'] = ['A|GENE1|100|1.2', 'TT|GENE1|101|1.3']
    infer_header_fields = infer_headers._InferHeaderFields(
        infer_headers=False, annotation_fields_to_infer=anno_fields)
    inferred_headers = next(infer_header_fields.process(variant, header))
    expected_types = {'CSQ_Gene_TYPE': 'String',
                      'CSQ_Position_TYPE': 'Integer',
                      'CSQ_Score_TYPE': 'Float'}
    for key, item in inferred_headers.infos.iteritems():
      self.assertEqual(item['type'], expected_types[key])
    self.assertEqual(len(expected_types), len(inferred_headers.infos))

  def test_infer_annotation_types_with_type_conflicts(self):
    anno_fields = ['CSQ']
    header = self._get_sample_header_fields(with_annotation=True)
    variant = self._get_sample_variant_1()
    variant.info['CSQ'] = ['A|1|100|1.2',
                           'A|2|101|1.3',
                           'A|1.2|start|0',
                           'TT|1.3|end|7']
    infer_header_fields = infer_headers._InferHeaderFields(False, anno_fields)
    inferred_headers = next(infer_header_fields.process(variant, header))
    expected_types = {'CSQ_Gene_TYPE': 'Float',
                      'CSQ_Position_TYPE': 'String',
                      'CSQ_Score_TYPE': 'Float'}
    for key, item in inferred_headers.infos.iteritems():
      self.assertEqual(item['type'], expected_types[key])
    self.assertEqual(len(expected_types), len(inferred_headers.infos))

  def test_infer_annotation_types_with_missing(self):
    anno_fields = ['CSQ']
    header = self._get_sample_header_fields(with_annotation=True)
    variant = self._get_sample_variant_1()
    variant.info['CSQ'] = ['A||100|',
                           'A||101|1.3',
                           'A|||1.4',
                           'TT|||']
    infer_header_fields = infer_headers._InferHeaderFields(False, anno_fields)
    inferred_headers = next(infer_header_fields.process(variant, header))
    expected_types = {'CSQ_Gene_TYPE': None,
                      'CSQ_Position_TYPE': 'Integer',
                      'CSQ_Score_TYPE': 'Float'}
    for key, item in inferred_headers.infos.iteritems():
      self.assertEqual(item['type'], expected_types[key])
    self.assertEqual(len(expected_types), len(inferred_headers.infos))

    variant.info['CSQ'] = []
    inferred_headers = next(infer_header_fields.process(variant, header))
    expected = vcf_header_io.VcfHeader()
    self.assertEqual(expected, inferred_headers)

  def test_infer_annotation_types_with_multiple_annotation_fields(self):
    anno_fields = ['CSQ', 'CSQ_VT']
    csq_vt = [('CSQ_VT', Info(
        'CSQ_VT',
        -1,
        'String',
        'Annotations from VEP. Format: Allele|Gene|Position|Score',
        'source',
        'v'))]
    header = self._get_sample_header_fields(with_annotation=csq_vt)
    variant = self._get_sample_variant_1()
    variant.info['CSQ_VT'] = ['A|1|100|1.2',
                              'A|2|101|1.3']
    variant.info['CSQ'] = ['A|1|100|1.2',
                           'A|2|101|1.3']
    infer_header_fields = infer_headers._InferHeaderFields(False, anno_fields)
    inferred_headers = next(infer_header_fields.process(variant, header))
    expected_types = {'CSQ_Gene_TYPE': 'Integer',
                      'CSQ_Position_TYPE': 'Integer',
                      'CSQ_Score_TYPE': 'Float',
                      'CSQ_VT_Gene_TYPE': 'Integer',
                      'CSQ_VT_Position_TYPE': 'Integer',
                      'CSQ_VT_Score_TYPE': 'Float'}
    for key, item in inferred_headers.infos.iteritems():
      self.assertEqual(item['type'], expected_types[key])
    self.assertEqual(len(expected_types), len(inferred_headers.infos))

  def test_infer_annotation_pipeline(self):
    anno_fields = ['CSQ']
    header = self._get_sample_header_fields(with_annotation=True)
    variant1 = self._get_sample_variant_1()
    variant1.info['CSQ'] = ['A|1|100|1.2',
                            'A|2|101|1.3',
                            'A|12|start|0',
                            'TT|13|end|7']
    variant2 = self._get_sample_variant_1()
    variant2.info['CSQ'] = ['A|1|100|',
                            'A|2|101|',
                            'A|1.2|102|0',
                            'TT|1.3|103|7']
    desc = 'Inferred type field for annotation {}.'
    expected = vcf_header_io.VcfHeader(infos={
        'CSQ_Gene_TYPE':
        Info('CSQ_Gene_TYPE', 1, 'Float', desc.format('Gene'), '', ''),
        'CSQ_Position_TYPE':
        Info('CSQ_Position_TYPE', 1, 'String',
             desc.format('Position'), '', ''),
        'CSQ_Score_TYPE':
        Info('CSQ_Score_TYPE', 1, 'Float', desc.format('Score'), '', '')})

    with TestPipeline() as p:
      inferred_headers = (
          p
          | Create([variant1, variant2])
          | 'InferAnnotationTypes' >>
          infer_headers.InferHeaderFields(
              defined_headers=header,
              infer_headers=False,
              annotation_fields_to_infer=anno_fields))
      assert_that(inferred_headers,
                  asserts.header_fields_equal_ignore_order([expected]))
      p.run()
