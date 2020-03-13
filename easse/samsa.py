from typing import List
from ucca.core import Passage

from easse.utils.ucca_utils import get_scenes_ucca, get_scenes_text, ucca_parse_texts
from easse.aligner.aligner import align
from easse.aligner.corenlp_utils import syntactic_parse_texts
import easse.utils.preprocessing as utils_prep

from tqdm import tqdm


def syntactic_parse_ucca_scenes(ucca_passages, verbose=False):
    # Gather all scenes together so as to make one single call to the syntactic parser
    scenes_per_passage = []
    all_scenes = []
    for passage in ucca_passages:
        scenes = get_scenes_text(passage)
        scenes_per_passage.append(len(scenes))
        all_scenes += scenes

    synt_parse_scenes = syntactic_parse_texts(all_scenes, verbose=verbose)

    gruped_scenes_per_passage = []
    start = 0
    for num_scenes in scenes_per_passage:
        gruped_scenes_per_passage.append(synt_parse_scenes[start:start + num_scenes])
        start += num_scenes

    assert len(gruped_scenes_per_passage) == len(ucca_passages)

    return gruped_scenes_per_passage


def align_scenes_sentences(synt_scenes, synt_sents, allow_mutiple_matches):
    scenes_sents_aligns = []
    already_matched = []
    for synt_scene in synt_scenes:
        max_sent_aligns = []
        for sent_num, synt_sent in enumerate(synt_sents):
            if not allow_mutiple_matches and sent_num in already_matched:
                continue
            word_alignments = align(synt_scene, synt_sent)[1]
            if len(word_alignments) > len(max_sent_aligns):
                max_sent_aligns = word_alignments
                max_sent_num = sent_num
        scenes_sents_aligns.append(max_sent_aligns)
        if len(max_sent_aligns) > 0:
            already_matched.append(max_sent_num)

    return scenes_sents_aligns


def _get_minimal_centers_from_scene(ucca_scene):
    minimal_centers = []
    main_relations = [edge.child for edge in ucca_scene.outgoing if edge.tag == 'P' or edge.tag == 'S']
    for relation in main_relations:
        relation_centers = [edge.child for edge in relation.outgoing if edge.tag == 'C']
        if relation_centers:
            while relation_centers:
                for center in relation_centers:
                    ccenters = [edge.child for edge in center.outgoing if edge.tag == 'C']
                lcenters = relation_centers
                relation_centers = ccenters
            minimal_centers.append(lcenters)
        else:  # they are already minimal centers
            minimal_centers.append(main_relations)
    return minimal_centers


def get_minimal_centers_from_relations(ucca_passage: Passage):
    """
    Return all the most internal centers of main relations in each passage
    """
    scenes = get_scenes_ucca(ucca_passage)
    minimal_centers = []
    for sc in scenes:
        minimal_centers += _get_minimal_centers_from_scene(sc)

    y = ucca_passage.layer("0")
    output = []
    for scp in minimal_centers:
        for par in scp:
            output2 = []
            positions = [d.position for d in par.get_terminals(False, True)]
            for pos in positions:
                if not output2:
                    output2.append(str(y.by_position(pos)))
                elif str(y.by_position(pos)) != output2[-1]:
                    output2.append(str(y.by_position(pos)))

        output.append(output2)

    return output


def get_minimal_centers_from_participants(P: Passage):
    """
    P is a ucca passage. Return all the minimal participant centers in each scene
    """
    scenes = get_scenes_ucca(P)
    n = []
    for sc in scenes:  # find participant nodes
        minimal_centers = []
        participants = [e.child for e in sc.outgoing if e.tag == 'A']
        for pa in participants:
            centers = [e.child for e in pa.outgoing if e.tag == 'C']
            if centers:
                while centers:
                    for c in centers:
                        ccenters = [e.child for e in c.outgoing if e.tag == 'C' or e.tag == 'P' or e.tag == 'S']   #also addresses center Scenes
                    lcenters = centers
                    centers = ccenters
                minimal_centers.append(lcenters)
            elif pa.is_scene():  # address the case of Participant Scenes
                scene_centers = [e.child for e in pa.outgoing if e.tag == 'P' or e.tag == 'S']
                for scc in scene_centers:
                    centers = [e.child for e in scc.outgoing if e.tag == 'C']
                    if centers:
                        while centers:
                            for c in centers:
                                ccenters = [e.child for e in c.outgoing if e.tag == 'C']
                            lcenters = centers
                            centers = ccenters
                        minimal_centers.append(lcenters)
                    else:
                        minimal_centers.append(scene_centers)
            elif any(e.tag == "H" for e in pa.outgoing):  # address the case of multiple parallel Scenes inside a participant
                hscenes = [e.child for e in pa.outgoing if e.tag == 'H']
                mh = []
                for h in hscenes:
                    hrelations = [e.child for e in h.outgoing if e.tag == 'P' or e.tag == 'S']  # in case of multiple parallel scenes we generate new multiple centers
                    for hr in hrelations:
                        centers = [e.child for e in hr.outgoing if e.tag == 'C']
                        if centers:
                            while centers:
                                for c in centers:
                                    ccenters = [e.child for e in c.outgoing if e.tag == 'C']
                                lcenters = centers
                                centers = ccenters
                            mh.append(lcenters[0])
                        else:
                            mh.append(hrelations[0])
                minimal_centers.append(mh)
            else:
                minimal_centers.append([pa])

        n.append(minimal_centers)

    y = P.layer("0")  # find cases of multiple centers
    output = []
    s = []
    I = []
    for scp in n:
        r = []
        u = n.index(scp)
        for par in scp:
            if len(par) > 1:
                d = scp.index(par)
                par = [par[i:i+1] for i in range(len(par))]
                for c in par:
                    r.append(c)
                I.append([u,d])
            else:
                r.append(par)
        s.append(r)

    for scp in s:  # find the spans of the participant nodes
        output1 = []
        for par in scp:
            # TODO: sometimes "par" does not contain anything, which caused the original implementation (without the if) to crash when unpacking
            if len(par) != 1:
                continue
            [par] = par
            output2 = []
            p = []
            d = par.get_terminals(False, True)
            for i in range(0, len(d)):
                p.append(d[i].position)

            for k in p:
                if len(output2) == 0:
                    output2.append(str(y.by_position(k)))
                elif str(y.by_position(k)) != output2[-1]:
                    output2.append(str(y.by_position(k)))
            output1.append(output2)
        output.append(output1)

    y = []  # unify spans in case of multiple centers
    for scp in output:
        x = []
        u = output.index(scp)
        for par in scp:
            for v in I:
                if par == output[v[0]][v[1]]:
                    for l in range(1,len(n[v[0]][v[1]])):
                        par.append((output[v[0]][v[1]+l])[0])

                    x.append(par)
                elif all(par != output[v[0]][v[1]+l] for l in range(1, len(n[v[0]][v[1]]))):
                    x.append(par)
            if not I:
                x.append(par)
        y.append(x)

    return y


def compute_samsa(orig_ucca_passage: Passage, orig_synt_scenes, sys_synt_sents):
    orig_scenes = get_scenes_text(orig_ucca_passage)

    num_orig_scenes = len(orig_scenes)
    num_sys_sents = len(sys_synt_sents)
    allow_mutiple_matches = num_orig_scenes > num_sys_sents

    score = 0.0
    if num_sys_sents <= num_orig_scenes:
        rel_min_centers = get_minimal_centers_from_relations(orig_ucca_passage)
        part_min_centers = get_minimal_centers_from_participants(orig_ucca_passage)

        orig_scenes_sys_sents_alignments = align_scenes_sentences(orig_synt_scenes, sys_synt_sents, allow_mutiple_matches)
        scorem = []
        scorea = []
        for scene_index, scene_sent_word_aligns in enumerate(orig_scenes_sys_sents_alignments):
            r = [scene_word for scene_word, _ in scene_sent_word_aligns]
            if not rel_min_centers[scene_index]:
                s = 0.5
            elif all(rel_min_centers[scene_index][l] in r for l in range(len(rel_min_centers[scene_index]))):
                s = 1.0
            else:
                s = 0.0
            scorem.append(s)

            sa = []
            if not part_min_centers[scene_index]:
                sa = [0.5]
                scorea.append(sa)
            else:
                for a in part_min_centers[scene_index]:
                    if not a:
                        p = 0.5
                    elif all(a[l] in r for l in range(len(a))):
                        p = 1
                    else:
                        p = 0
                    sa.append(p)
                scorea.append(sa)

        scoresc = []
        for i in range(num_orig_scenes):
            d = len(scorea[i])
            v = 0.5 * scorem[i] + 0.5 * (1 / d) * sum(scorea[i])
            scoresc.append(v)
        score = (num_sys_sents / (num_orig_scenes ** 2)) * sum(scoresc)
    return score


def corpus_samsa(orig_sents: List[str], sys_sents: List[str], lowercase: bool = False, tokenizer: str = '13a',
                 verbose: bool = False):

    print('Warning: SAMSA metric is long to compute (120 sentences ~ 1h), disable it if you need fast evaluation.')
    
    orig_sents = [utils_prep.normalize(sent, lowercase, tokenizer) for sent in orig_sents]
    orig_ucca_passages = ucca_parse_texts(orig_sents)
    orig_synt_scenes = syntactic_parse_ucca_scenes(orig_ucca_passages, verbose=verbose)

    sys_sents = [utils_prep.normalize(output, lowercase, tokenizer) for output in sys_sents]
    sys_sents_synt = syntactic_parse_texts(sys_sents, tokenize=False, sentence_split=True, verbose=verbose)

    samsa_score = 0.0
    for orig_passage, orig_scenes, sys_synt in tqdm(zip(orig_ucca_passages, orig_synt_scenes, sys_sents_synt),
                                            disable=(not verbose)):
        samsa_score += compute_samsa(orig_passage, orig_scenes, sys_synt)

    samsa_score /= len(orig_sents)

    return 100. * samsa_score


def sentence_samsa(orig_sent: str, sys_sent: str, lowercase: bool = False, tokenizer: str = '13a',
                   verbose: bool = False):
    return corpus_samsa([orig_sent], [sys_sent], lowercase, tokenizer, verbose)
