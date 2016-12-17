from pyramid.view import view_config

from sqlalchemy import (
    and_,
)

from sqlalchemy.orm import aliased

from lingvodoc.models import (
    DBSession,
    Entity,
    LexicalEntry,
)

from pyramid.httpexceptions import (
    HTTPOk
)

from pyramid.response import FileIter, Response

import chardet
import pydub
import pydub.utils
import pympi
import xlwt

import io
import tempfile
import urllib.request
import urllib.parse

import logging
log = logging.getLogger(__name__)


def find_max_segment(wav_url, segment_list, type = 'rms'):
    """
    Accepts URL to a WAV file and a list of segments specified by boundaries in seconds, returns index of
    the segment with the highest intensity, relative intensity of this segment, index of the longest segment
    and the length of the longest segment.

    Intensity can be measured either as mean absolute intensity, or a root mean squared intesity. Choice of
    the intensity computation method is controlled by a third parameter with default value of 'rms' meaning
    root mean squared intensity. Other possible value is 'mean_abs', meaning mean absolute intesity.
    """

    if not segment_list:
        return None

    # Setting intensity measure function.

    rms_f = lambda segment: segment.rms

    def mean_abs_f(segment):
        sample_list = segment.get_array_of_samples()
        return int(sum(abs(sample) for sample in sample_list) / len(sample_list))

    if type == 'rms':
        intensity_f = rms_f
    elif type == 'mean_abs':
        intensity_f = mean_abs_f
    else:
        raise ValueError()

    # Finding loudest and longest segments.

    max_intensity = None
    max_intensity_index = None

    max_length = None
    max_length_index = None

    # Partially inspired by source code at scripts/convert_five_tiers.py:307.

    with tempfile.NamedTemporaryFile() as temp_file:

        sound_file = urllib.request.urlopen(urllib.parse.quote(wav_url, safe = '/:'))
        temp_file.write(sound_file.read())
        temp_file.flush()

        sound = pydub.AudioSegment.from_wav(temp_file.name)

        for index, (begin_sec, end_sec, _) in enumerate(segment_list):

            # Pydub's AudioSegment references sound locations in milliseconds, see
            # https://github.com/jiaaro/pydub/blob/master/API.markdown.

            intensity = intensity_f(sound[begin_sec * 1000 : end_sec * 1000])
            length = end_sec - begin_sec

            if max_intensity == None or intensity > max_intensity:
                max_intensity = intensity
                max_intensity_index = index

            if max_length == None or length > max_length:
                max_length = length
                max_length_index = index

    return (max_intensity_index,
        float(max_intensity) / intensity_f(sound),
        max_length_index,
        max_length)


#: Set of vowels used by computation of phonology of dictionary perspectives.
vowel_set = set('iyɨʉɯuɪʏɪ̈ʊ̈ɯ̽ʊeøɘɵɤoəɛœɜɞʌɔæɐaɶɑɒ')


@view_config(route_name="phonology", renderer='json')
def phonology(request):
    """
    Computes phonology of a specified perspective.

    Perspective is specified by request parameters 'perspective_client_id' and 'perspective_object_id',
    example of a request: /phonology?perspective_client_id=345&perspective_object_id=2.
    """

    perspective_cid = request.params.get('perspective_client_id')
    perspective_oid = request.params.get('perspective_object_id')

    limit = (None if 'limit' not in request.params else
        int(request.params.get('limit')))

    limit_exception = (None if 'limit_exception' not in request.params else
        int(request.params.get('limit_exception')))

    limit_no_vowel = (None if 'limit_no_vowel' not in request.params else
        int(request.params.get('limit_no_vowel')))

    limit_result = (None if 'limit_result' not in request.params else
        int(request.params.get('limit_result')))

    # TODO: get perspective's translation and language it belongs to.
    # We get lexical entries of this perspective with markup'ed sounds.

    Sound = aliased(Entity, name="Sound")
    query = DBSession.query(LexicalEntry, Entity, Sound).filter(and_(
        LexicalEntry.parent_client_id == perspective_cid,
        LexicalEntry.parent_object_id == perspective_oid,
        Entity.parent_client_id == LexicalEntry.client_id,
        Entity.parent_object_id == LexicalEntry.object_id,
        Entity.additional_metadata.contains({"data_type": "praat markup"}),
        Sound.client_id == Entity.self_client_id,
        Sound.object_id == Entity.self_object_id))

    # We process these lexical entries in batches. Just in case, it seems that perspectives rarely have more
    # then several hundred such lexical entries.

    exception_counter = 0
    no_vowel_counter = 0
    result_list = list()

    for index, row in enumerate(query.yield_per(100)):
      try:

        markup_url = row.Entity.content
        sound_url = row.Sound.content

        markup_bytes = urllib.request.urlopen(urllib.parse.quote(markup_url, safe = '/:')).read()

        textgrid = pympi.Praat.TextGrid(xmax = 0)
        textgrid.from_file(io.BytesIO(markup_bytes), codec = chardet.detect(markup_bytes)['encoding'])

        # If the markup does not have any vowels, we skip it.

        interval_list = textgrid.get_tier(0).get_all_intervals()
        transcription = ''.join(text for begin, end, text in interval_list)

        if all(character not in vowel_set for character in transcription):
            no_vowel_counter += 1

            if (limit_no_vowel and no_vowel_counter >= limit_no_vowel or
                limit and index + 1 >= limit):
                break

            continue

        (max_intensity_index, max_intensity, max_length_index, max_length) = \
            find_max_segment(sound_url, interval_list)

        max_intensity_interval = interval_list[max_intensity_index]
        max_length_interval = interval_list[max_length_index]

        # Otherwise we've got outselves another result.

        max_length_str = '{0} {1:.3f} [{2}]'.format(
            max_length_interval[2], max_length,
            len(''.join(text for begin, end, text in interval_list[:max_length_index])) + 1)

        max_intensity_str = '{0} {1}{2:.3f} [{3}]'.format(
            max_intensity_interval[2],
            '+' if max_intensity_index == max_length_index else '-',
            max_intensity,
            len(''.join(text for begin, end, text in interval_list[:max_intensity_index])) + 1)

        log.debug('{0}:\n{1}\n{2}\n{3}'.format(
            index, markup_url, sound_url,
            (transcription, max_length_str, max_intensity_str)))

        result_list.append((transcription, max_length_str, max_intensity_str))

        if (limit_result and len(result_list) >= limit_result or
            limit and index + 1 >= limit):
            break

      except:
        exception_counter += 1

        if (limit_exception and exception_counter >= limit_exception or
            limit and index + 1 >= limit):
            break

    log.debug('phonology {0}/{1}: {2} results, {3} no vowels, {4} exceptions'.format(
        perspective_cid, perspective_oid, len(result_list), no_vowel_counter, exception_counter))

    # If we have no results, we indicate the situation and also show number of failures and number of
    # markups with no vowels.

    if not result_list:
        return {
            "error": "no markups for this query",
            "exception_counter": exception_counter,
            "no_vowel_counter": no_vowel_counter}

    # Otherwise we create and then serve Excel file.

    excel_book = xlwt.Workbook(encoding = "utf-8")
    sheet = excel_book.add_sheet("Sheet 1")

    for index, (transcription, max_length_str, max_intensity_str) in enumerate(result_list):
        sheet.write(index, 0, transcription)
        sheet.write(index, 1, max_length_str)
        sheet.write(index, 2, max_intensity_str)

    excel_stream = io.BytesIO()
    excel_book.save(excel_stream)
    excel_stream.seek(0)

    # See http://stackoverflow.com/questions/2937465/what-is-correct-content-type-for-excel-files for Excel
    # content-type.

    response = Response(content_type = 'application/vnd.ms-excel')

    response.app_iter = FileIter(excel_stream)
    response.headers['Content-Disposition'] = "attachment; filename=phonology.xls"

    return response

    # 1. Get intervals list with symbols
    # 2. Check the intervals where the following symbols present:
    #       i y ɨ ʉ ɯ u ɪ ʏ ɪ̈ ʊ̈ ɯ̽ ʊ e ø ɘ ɵ ɤ o ə ɛ œ ɜ ɞ ʌ ɔ æ ɐ a ɶ ɑ ɒ
    # 3. a) If any of the symbols present in any markup interval,
    #       get the intervals for these matches and goto 4.
    #    b) Else (none of the symbols are found in markup), continue the cycle (skip this markup-sound pair)
    # 4. Download the sound and find_max_db_segment with these intervals
    # 5. Form the table row:
    #   transcription (concat the symbols in all intervals without whitespaces) - e.g. "pilka"
    #   symbol with the max length, its length in seconds, its position in transcription - e.g. "i 0.072 [2]"
    #   symbol with max intensity, its intensity, its position - e.g. "i -0.68 [2]"
    #   mark "+" or "-" for if max length and max intensity symbol is the same interval (i [2] in this case)
    # 6. Output is an Excel file (do save them when you test) or {"error": "no markups for this query"} .


# A little bit of testing.
if __name__ == '__main__':

    wav_url = 'http://www.wav-sounds.com/answering_machine/rappin.wav'
    print('rms', find_max_db_segment(wav_url, [(0.1, 0.3), (0.4, 0.5)]))
    print('mean_abs', find_max_db_segment(wav_url, [(0.1, 0.3), (0.4, 0.5)], 'mean_abs'))

    wav_url = 'http://www.wav-sounds.com/movie/terminator.wav'
    print('rms', find_max_db_segment(wav_url, [(0.1, 0.3), (0.4, 0.5)]))
    print('mean_abs', find_max_db_segment(wav_url, [(0.1, 0.3), (0.4, 0.5)], 'mean_abs'))

