import os.path as op
import numpy as np
from itertools import product
import shutil
import glob
from src.utils import utils
from src.utils import labels_utils as lu
from src.preproc import anatomy as anat
from src.preproc import meg as meg


LINKS_DIR = utils.get_links_dir()
SUBJECTS_DIR = utils.get_link_dir(LINKS_DIR, 'subjects', 'SUBJECTS_DIR')
MEG_DIR = utils.get_link_dir(LINKS_DIR, 'meg')
MMVT_DIR = utils.get_link_dir(LINKS_DIR, 'mmvt')


def prepare_files(args):
    ret = {}
    for subject in args.subject:
        ret[subject] = True
        for task in args.tasks:
            fol = utils.make_dir(op.join(MEG_DIR, task, subject))
            local_epo_fname = op.join(fol, '{}_{}_Onset-epo.fif'.format(subject, task))
            if not op.isfile(local_epo_fname):
                remote_epo_fname = op.join(args.meg_dir, subject, '{}_{}_Onset-epo.fif'.format(subject, task))
                print('Creating a local link to {}'.format(remote_epo_fname))
                utils.make_link(remote_epo_fname, local_epo_fname)
            local_raw_fname = op.join(fol, '{}_{}-raw.fif'.format(subject, task))
            if not op.isfile(local_raw_fname):
                remote_raw_fname = op.join(
                    utils.get_parent_fol(args.meg_dir), 'ica', subject, '{}_{}-raw.fif'.format(subject, task))
                print('Creating a local link to {}'.format(remote_raw_fname))
                utils.make_link(remote_raw_fname, local_raw_fname)
        ret[subject] = ret[subject] and op.isfile(local_epo_fname) and op.isfile(local_raw_fname)
    print('Good subjects:')
    print([s for s, r in ret.items() if r])
    print('Bad subjects:')
    print([s for s, r in ret.items() if not r])


def anatomy_preproc(args, subject=''):
    args = anat.read_cmd_args(dict(
        subject=args.subject if subject == '' else subject,
        remote_subject_dir='/autofs/space/lilli_001/users/DARPA-Recons/{subject}',
        high_level_atlas_name='darpa_atlas',
        function='create_annotation,create_high_level_atlas',
        ignore_missing=True
    ))
    anat.call_main(args)


def get_empty_fnames(subject, tasks, args):
    utils.make_dir(op.join(MEG_DIR, subject))
    utils.make_link(op.join(args.remote_subject_dir.format(subject=subject), 'bem'),
                    op.join(MEG_DIR, subject, 'bem'))
    for task in tasks:
        utils.make_dir(op.join(MEG_DIR, task, subject))
        utils.make_link(op.join(MEG_DIR, subject, 'bem'), op.join(MEG_DIR, task, subject, 'bem'))
    utils.make_link(op.join(MEG_DIR, subject, 'bem'), op.join(SUBJECTS_DIR, subject, 'bem'))

    remote_meg_fol = '/autofs/space/lilli_003/users/DARPA-TRANSFER/meg/{}'.format(subject)
    csv_fname = op.join(remote_meg_fol, 'cfg.txt')
    if not op.isfile(csv_fname):
        print('No cfg file!')
        return {task:'' for task in tasks}
    days, empty_fnames, cors = {}, {}, {}
    for line in utils.csv_file_reader(csv_fname, ' '):
        for task in tasks:
            if line[4].lower() == task.lower():
                days[task] = line[2]
    print(days)
    for line in utils.csv_file_reader(csv_fname, ' '):
        if line[4] == 'empty':
            for task in tasks:
                empty_fnames[task] = op.join(MEG_DIR, task, subject, '{}_empty_raw.fif'.format(subject))
                if op.isfile(empty_fnames[task]):
                    continue
                task_day = days[task]
                if line[2] == task_day:
                    empty_fname = op.join(remote_meg_fol, line[0].zfill(3), line[-1])
                    if not op.isfile(empty_fname):
                        raise Exception('empty file does not exist! {}'.format(empty_fname[task]))
                    utils.make_link(empty_fname, empty_fnames[task])
    cor_dir = op.join(args.remote_subject_dir.format(subject=subject), 'mri', 'T1-neuromag', 'sets')
    for task in tasks:
        if op.isfile(op.join(cor_dir, 'COR-{}-{}.fif'.format(subject, task.lower()))):
            cors[task] = op.join(cor_dir, 'COR-{}-{}.fif'.format('{subject}', task.lower()))
        elif op.isfile(op.join(cor_dir, 'COR-{}-day{}.fif'.format(subject, days[task]))):
            cors[task] = op.join(cor_dir, 'COR-{}-day{}.fif'.format('{subject}', days[task]))
    return empty_fnames, cors, days

#
# def calc_meg_epochs(args):
#     empty_fnames, cors, days = get_empty_fnames(args.subject[0], args.tasks, args)
#     times = (-2, 4)
#     for task in args.tasks:
#         args = meg.read_cmd_args(dict(
#             subject=args.subject, mri_subject=args.subject,
#             task=task,
#             remote_subject_dir='/autofs/space/lilli_001/users/DARPA-Recons/{subject}',
#             get_task_defaults=False,
#             fname_format='{}_{}_nTSSS-ica-raw'.format('{subject}', task.lower()),
#             empty_fname=empty_fnames[task],
#             function='calc_epochs,calc_evokes',
#             conditions=task.lower(),
#             data_per_task=True,
#             normalize_data=False,
#             t_min=times[0], t_max=times[1],
#             read_events_from_file=False, stim_channels='STI001',
#             use_empty_room_for_noise_cov=True,
#             n_jobs=args.n_jobs
#         ))
#         meg.call_main(args)


def meg_preproc(args, overwrite=False):
    inv_method, em = 'MNE', 'mean_flip'
    atlas = 'darpa_atlas'
    bands = dict(theta=[4, 8], alpha=[8, 15], beta=[15, 30], gamma=[30, 55], high_gamma=[65, 200])
    prepare_files(args)
    times = (-2, 4)

    subjects = args.subject
    for subject in subjects:
        # if not utils.both_hemi_files_exist(op.join(SUBJECTS_DIR, subject, 'label', '{hemi}.darpa_atlas.annot')):
        anatomy_preproc(args, subject)
        if not utils.both_hemi_files_exist(op.join(SUBJECTS_DIR, subject, 'label', '{}.{}.annot'.format('{hemi}', atlas))):
            print('Can\'t find the atlas {}!'.format(atlas))
            continue
        empty_fnames, cors, days = get_empty_fnames(subject, args.tasks, args)
        args.subject = subject
        for task in args.tasks:
            if task not in cors:
                print('{} no in get_empty_fnames!'.format(task))
                continue
            output_fname = op.join(
                MMVT_DIR, subject, 'meg', 'labels_data_{}_{}_{}_{}_minmax.npz'.format(
                    task.lower(), atlas, inv_method, em))
            if op.isfile(output_fname) and not overwrite:
                print('{} already exist!'.format(output_fname))
                continue
            meg_args = meg.read_cmd_args(dict(
                subject=args.subject, mri_subject=args.subject,
                task=task, inverse_method=inv_method, extract_mode=em, atlas=atlas,
                # meg_dir=args.meg_dir,
                remote_subject_dir=args.remote_subject_dir, # Needed for finding COR
                get_task_defaults=False,
                fname_format='{}_{}_Onset'.format('{subject}', task),
                raw_fname=op.join(MEG_DIR, task, subject, '{}_{}-raw.fif'.format(subject, task)),
                epo_fname=op.join(MEG_DIR, task, subject, '{}_{}_Onset-epo.fif'.format(subject, task)),
                empty_fname=empty_fnames[task],
                function='calc_evokes,make_forward_solution,calc_inverse_operator,calc_stc,calc_labels_avg_per_condition,calc_labels_min_max',
                # function='calc_epochs',
                # function='calc_labels_connectivity',
                conditions=task.lower(),
                cor_fname=cors[task].format(subject=subject),
                average_per_event=False,
                data_per_task=True,
                ica_overwrite_raw=False,
                normalize_data=False,
                t_min=times[0], t_max=times[1],
                read_events_from_file=False, stim_channels='STI001',
                use_empty_room_for_noise_cov=True,
                calc_source_band_induced_mean_power=False,
                calc_inducde_mean_power_per_label=False,
                bands='', #dict(theta=[4, 8], alpha=[8, 15], beta=[15, 30], gamma=[30, 55], high_gamma=[65, 200]),
                con_method='coh',
                con_mode='cwt_morlet',
                overwrite_connectivity=False,
                read_only_from_annot=False,
                # pick_ori='normal',
                # overwrite_epochs=True,
                # overwrite_evoked=True,
                # overwrite_inv=True,
                # overwrite_stc=True,
                # overwrite_labels_data=True,
                n_jobs=args.n_jobs
            ))
            meg.call_main(meg_args)

    good_subjects = [s for s in subjects if
           op.isfile(op.join(MMVT_DIR, subject, 'meg',
                             'labels_data_msit_{}_{}_{}_minmax.npz'.format(atlas, inv_method, em))) and
           op.isfile(op.join(MMVT_DIR, subject, 'meg',
                             'labels_data_ecr_{}_{}_{}_minmax.npz'.format(atlas, inv_method, em)))]
    print('Good subjects:')
    print(good_subjects)
    print('Bad subjects:')
    print(list(set(subjects) - set(good_subjects)))


def post_meg_preproc(args):
    inv_method, em = 'MNE', 'mean_flip'
    atlas = 'darpa_atlas'
    bands = dict(theta=[4, 8], alpha=[8, 15], beta=[15, 30], gamma=[30, 55], high_gamma=[65, 200])
    times = (-2, 4)

    subjects = args.subject
    res_fol = utils.make_dir(op.join(utils.get_parent_fol(MMVT_DIR), 'msit-ecr'))
    for subject in subjects:
        args.subject = subject
        for task in args.tasks:
            task = task.lower()
            if not utils.both_hemi_files_exist(
                    op.join(MMVT_DIR, subject, 'meg', 'labels_data_{}_{}_{}_{}_lh.npz'.format(
                        task, atlas, inv_method, em, '{hemi}'))):
                print('label data can\'t be found for {} {}'.format(subject, task))
                continue
            utils.make_dir(op.join(res_fol, subject))
            meg.calc_labels_func(subject, task, atlas, inv_method, em, tmin=0, tmax=0.5, times=times, norm_data=False)
            meg.calc_labels_mean_power_bands(subject, task, atlas, inv_method, em, tmin=times[0], tmax=times[1], overwrite=True)

        for fname in [f for f in glob.glob(op.join(MMVT_DIR, subject, 'labels', 'labels_data', '*')) if op.isfile(f)]:
            shutil.copyfile(fname, op.join(res_fol, subject, utils.namebase_with_ext(fname)))


def post_analysis(args):
    import matplotlib.pyplot as plt
    from collections import defaultdict
    atlas = 'darpa_atlas'
    res_fol = utils.make_dir(op.join(utils.get_parent_fol(MMVT_DIR), 'msit-ecr'))
    bands = dict(theta=[4, 8], alpha=[8, 15], beta=[15, 30], gamma=[30, 55], high_gamma=[65, 200])
    data_dic = np.load(op.join(res_fol, 'data_dictionary.npz'))
    meta_data = data_dic['noam_dict'].tolist()
    # brain_overall_res_fname = op.join(res_fol, 'brain_overall_res.npz')
    subjects1 = set(meta_data[0]['MSIT'].keys())
    subjects2 = set(meta_data[1]['MSIT'].keys())
    subjects_with_data = defaultdict(list)
    mean_evo = {group_id:defaultdict(list) for group_id in range(2)}
    mean_power = {group_id: {} for group_id in range(2)}
    power = {group_id: {} for group_id in range(2)}
    for group_id in range(2):
        for task in args.tasks:
            mean_power[group_id][task] = defaultdict(list)
            power[group_id][task] = {band: None for band in bands.keys()}
        for subject in meta_data[group_id]['ECR'].keys():
            if not op.isdir(op.join(res_fol, subject)):
                print('No folder data for {}'.format(subject))
                continue
            for task in args.tasks:
                mean_fname = op.join(res_fol, subject, '{}_{}_mean.npz'.format(task.lower(), atlas))
                if op.isfile(mean_fname):
                    d = utils.Bag(np.load(mean_fname))
                    mean_evo[group_id][task].append(d.data.mean())
                for band in bands.keys():
                    if power[group_id][task][band] is None:
                        power[group_id][task][band] = defaultdict(list)
                    mean_power_fname = op.join(res_fol, subject, '{}_power_{}.npz'.format(task.lower(), band))
                    if op.isfile(mean_power_fname):
                        d = utils.Bag(np.load(mean_power_fname))
                        mean_power[group_id][task][band].append(d.data.mean())
                        for label_id, label in enumerate(d.names):
                            power[group_id][task][band][label].append(d.data[label_id])

    for group_id in range(2):
        x = [np.array(mean_evo[group_id][task]) for task in args.tasks]
        # x = [_x[_x < np.percentile(_x, 90)] for _x in x]
        ttest(x[0], x[1])

    for band in bands.keys():
        # fig, (ax1, ax2) = plt.subplots(1, 2, sharey=True)
        for group_id in range(2): #, ax in zip(range(2), [ax1, ax2]):
            subjects_with_data[group_id] = np.array(subjects_with_data[group_id])
            print()
            x = [np.array(mean_power[group_id][task][band]) for task in args.tasks]
            x = [_x[_x < np.percentile(_x, 90)] for _x in x]
            # ttest(x[0], x[1], title='group {} band {}'.format(group_id, band))

            for label_id, label in enumerate(d.names):
                x = [np.array(power[group_id][task][band][label]) for task in args.tasks]
                x = [_x[_x < np.percentile(_x, 95)] for _x in x]
                ttest(x[0], x[1], alpha=0.01, title='group {} band {} label {}'.format(group_id, band, label))
        # f, (ax1, ax2) = plt.subplots(2, 1)
            # ax1.hist(x[0])
            # ax2.hist(x[1])
            # plt.show()
            # ax.set_title('group {}'.format(group_id))
            # ax.bar(np.arange(2), [np.mean(mean_power[group_id][task][band]) for task in args.tasks])
            # ax.set_xticklabels(args.tasks, rotation=30)
        # fig.suptitle('{} mean_power'.format(band))
        # plt.show()


def ttest(x1, x2, two_tailed_test=True, alpha=0.05, is_greater=True, title=''):
    import scipy.stats
    t, pval = scipy.stats.ttest_ind(x1, x2, equal_var=True)
    sig = is_significant(pval, t, two_tailed_test, alpha, is_greater)
    welch_t, welch_pval = scipy.stats.ttest_ind(x1, x2, equal_var=False)
    welch_sig = is_significant(pval, t, two_tailed_test, alpha, is_greater)
    if sig or welch_sig:
        print('{}: {:.2f}+-{:.2f}, {:.2f}+-{:.2f}'.format(title, np.mean(x1), np.std(x1), np.mean(x2), np.std(x2)))
        print('test: pval: {:.4f} sig: {}. welch: pval: {:.4f} sig: {}'.format(pval, sig, welch_pval, welch_sig))


def is_significant(pval, t, two_tailed_test, alpha=0.05, is_greater=True):
    if two_tailed_test:
        return pval < alpha
    else:
        if is_greater:
            return pval / 2 < alpha and t > 0
        else:
            return pval / 2 < alpha and t < 0

    # for subject, task, band in product(args.subject, tasks, bands.keys()):
    #     mean_power_fol = op.join(MMVT_DIR, subject, 'labels', 'labels_data')
    #     d = utils.Bag(np.load(op.join(mean_power_fol, '{}_mean_power_{}.npz'.format(task.lower(), band))))
    #     for label_name, label_data in zip(d.names, d.data):
    #         hemi = lu.get_label_hemi(label_name)
    #         plt.figure()
    #         plt.axhline(label_data * 1e5, color='r', linestyle='--')
    #         plt.show()
    #         plt.close()
    #         print('asdf')
    #



if __name__ == '__main__':
    import argparse
    from src.utils import args_utils as au
    parser = argparse.ArgumentParser(description='MMVT')
    parser.add_argument('-s', '--subject', help='subject name', required=True, type=au.str_arr_type)
    parser.add_argument('-f', '--function', help='function name', required=False, default='meg_preproc')
    parser.add_argument('-t', '--tasks', help='tasks', required=False, default='MSIT,ECR', type=au.str_arr_type)
    parser.add_argument('--meg_dir', required=False,
                        default='/autofs/space/karima_001/users/alex/MSIT_ECR_Preprocesing_for_Noam/epochs')
                        # default='/autofs/space/karima_001/users/alex/MSIT_ECR_Preprocesing_for_Noam/raw_preprocessed')
    parser.add_argument('--remote_subject_dir', required=False,
                        default='/autofs/space/lilli_001/users/DARPA-Recons/{subject}')
    parser.add_argument('--n_jobs', help='cpu num', required=False, default=-1)
    args = utils.Bag(au.parse_parser(parser))

    if args.subject[0] == 'all':
        args.subject = [utils.namebase(d) for d in glob.glob(op.join(args.meg_dir, '*')) if op.isdir(d) and
                        op.isfile(op.join(d, '{}_{}_Onset-epo.fif'.format(utils.namebase(d), 'ECR'))) and
                        op.isfile(op.join(d, '{}_{}_Onset-epo.fif'.format(utils.namebase(d), 'MSIT')))]
        print('{} subjects were found with both tasks!'.format(len(args.subject)))
    locals()[args.function](args)
