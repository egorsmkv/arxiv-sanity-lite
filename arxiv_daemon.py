"""
This script is intended to wake up every 30 min or so (eg via cron),
it checks for any new arxiv papers via the arxiv API and stashes
them into a sqlite database.
"""

import sys
import time
import random
import logging
import argparse

from aslite.arxiv import get_response, parse_response
from aslite.db import get_papers_db, get_metas_db

CS = '''cs.AI - Artificial Intelligence
cs.CL - Computation and Language
cs.CC - Computational Complexity
cs.CE - Computational Engineering, Finance, and Science
cs.CG - Computational Geometry
cs.GT - Computer Science and Game Theory
cs.CV - Computer Vision and Pattern Recognition
cs.CY - Computers and Society
cs.CR - Cryptography and Security
cs.DS - Data Structures and Algorithms
cs.DB - Databases
cs.DL - Digital Libraries
cs.DM - Discrete Mathematics
cs.DC - Distributed, Parallel, and Cluster Computing
cs.ET - Emerging Technologies
cs.FL - Formal Languages and Automata Theory
cs.GL - General Literature
cs.GR - Graphics
cs.AR - Hardware Architecture
cs.HC - Human-Computer Interaction
cs.IR - Information Retrieval
cs.IT - Information Theory
cs.LO - Logic in Computer Science
cs.LG - Machine Learning
cs.MS - Mathematical Software
cs.MA - Multiagent Systems
cs.MM - Multimedia
cs.NI - Networking and Internet Architecture
cs.NE - Neural and Evolutionary Computing
cs.NA - Numerical Analysis
cs.OS - Operating Systems
cs.OH - Other Computer Science
cs.PF - Performance
cs.PL - Programming Languages
cs.RO - Robotics
cs.SI - Social and Information Networks
cs.SE - Software Engineering
cs.SD - Sound
cs.SC - Symbolic Computation
cs.SY - Systems and Control'''.splitlines()
CS = [x.split(' - ')[0] for x in CS]
CS = ['cat:' + x + '+OR+' for x in CS]
CS = ''.join(CS)[:-4] # [:-4] removes "+OR+" sequence at the end

if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO, format='%(name)s %(levelname)s %(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')

    parser = argparse.ArgumentParser(description='Arxiv Daemon')
    parser.add_argument('-n', '--num', type=int, default=100, help='up to how many papers to fetch')
    parser.add_argument('-s', '--start', type=int, default=0, help='start at what index')
    parser.add_argument('-b', '--break-after', type=int, default=3, help='how many 0 new papers in a row would cause us to stop early? or 0 to disable.')
    args = parser.parse_args()
    print(args)
    """
    Quick note on the break_after argument: In a typical setting where one wants to update
    the papers database you'd choose a slightly higher num, but then break out early in case
    we've reached older papers that are already part of the database, to spare the arxiv API.
    """

    # query string of papers to look for
    # q = 'cat:cs.CV+OR+cat:cs.LG+OR+cat:cs.CL+OR+cat:cs.AI+OR+cat:cs.NE+OR+cat:cs.RO'
    q = 'cat:eess.AS+OR+cat:cs.SD'

    pdb = get_papers_db(flag='c')
    mdb = get_metas_db(flag='c')
    prevn = len(pdb)

    def store(p):
        pdb[p['_id']] = p
        mdb[p['_id']] = {'_time': p['_time']}

    # fetch the latest papers
    total_updated = 0
    zero_updates_in_a_row = 0
    for k in range(args.start, args.start + args.num, 100):
        logging.info('querying arxiv api for query %s at start_index %d' % (q, k))

        # attempt to fetch a batch of papers from arxiv api
        ntried = 0
        while True:
            try:
                resp = get_response(search_query=q, start_index=k)
                papers = parse_response(resp)
                time.sleep(0.5)
                if len(papers) == 100:
                    break # otherwise we have to try again
            except Exception as e:
                logging.warning(e)
                logging.warning("will try again in a bit...")
                ntried += 1
                if ntried > 1000:
                    logging.error("ok we tried 1,000 times, something is srsly wrong. exitting.")
                    sys.exit()
                time.sleep(2 + random.uniform(0, 4))

        # process the batch of retrieved papers
        nhad, nnew, nreplace = 0, 0, 0
        for p in papers:
            pid = p['_id']
            if pid in pdb:
                if p['_time'] > pdb[pid]['_time']:
                    # replace, this one is newer
                    store(p)
                    nreplace += 1
                else:
                    # we already had this paper, nothing to do
                    nhad += 1
            else:
                # new, simple store into database
                store(p)
                nnew += 1
        prevn = len(pdb)
        total_updated += nreplace + nnew

        # some diagnostic information on how things are coming along
        logging.info(papers[0]['_time_str'])
        logging.info("k=%d, out of %d: had %d, replaced %d, new %d. now have: %d" %
             (k, len(papers), nhad, nreplace, nnew, prevn))

        # early termination criteria
        if nnew == 0:
            zero_updates_in_a_row += 1
            if args.break_after > 0 and zero_updates_in_a_row >= args.break_after:
                logging.info("breaking out early, no new papers %d times in a row" % (args.break_after, ))
                break
            elif k == 0:
                logging.info("our very first call for the latest there were no new papers, exitting")
                break
        else:
            zero_updates_in_a_row = 0

        # zzz
        time.sleep(1 + random.uniform(0, 3))

    # exit with OK status if anything at all changed, but if nothing happened then raise 1
    sys.exit(0 if total_updated > 0 else 1)
