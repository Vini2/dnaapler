import os
import sys
import subprocess as sp
from Bio import SeqIO
from Bio.SeqRecord import SeqRecord
import pandas as pd
from loguru import logger
import click


def process_blast_output_and_reorient(
    input, blast_file, out_file, ctx: click.Context, gene: str
):
    # defin colnames
    col_list = [
        "qseqid",
        "qlen",
        "sseqid",
        "slen",
        "length",
        "qstart",
        "qend",
        "sstart",
        "send",
        "pident",
        "nident",
        "gaps",
        "mismatch",
        "evalue",
        "bitscore",
        "qseq",
        "sseq",
    ]
    # read in the dataframe from BLAST
    try:
        blast_df = pd.read_csv(
            blast_file, delimiter="\t", index_col=False, names=col_list
        )
    except:
        logger.error(f"There was an issue with parsing the BLAST output file.")
        ctx.exit(2)

    ###### top hit has a start of 1 ########
    # take the top hit - blast sorts by bitscore
    # if the start is 1 of the top hit
    if blast_df["qstart"][0] == 1:
        logger.error(
            f"Based on the BLAST output top hit, your input is already oriented to begin with {gene}."
        )
        ctx.exit(2)

    ###### top hit ########
    # prokaryotes can use AUG M, GUG V or UUG L as start codons - for Pseudomonas aeruginosa PA01  dnaA actually starts with V
    # Therefore, I will require the start codon to be the 1st in the searched sequence match - unlikely to not be but nonetheless
    ########### Sometimes, the top hit might not be the actual gene of interest (e.g. in phages if the terL is disrupted - like SAOMS1)
    # so in these cases, go down the list and check there is a hit with a legitimate start codon
    # I anticipate this will be rare usually, the first will be it :)
    else:
        gene_found = False
        for i in range(0, len(blast_df.qseq)):
            if blast_df["qseq"][i][0] in ["M", "V", "L"] and (
                blast_df["sstart"][i] == 1
            ):
                reorient_sequence(blast_df, input, out_file, gene, i)
                # warn if the top hit not used
                if i >= 1:
                    logger.warning(
                        f"The top {gene} blastx hit was not chosen to reorient your genome, as it did not begin with a valid start codon."
                    )
                    logger.warning(
                        f"A lower hit had a valid start codon which was used instead."
                    )
                gene_found = True
                break
        if gene_found == False:
            logger.info(
                f"{gene} start not identified. Please check your input file or try dnaapler custom. If you have assembled an unusual species, this may also cause this error."
            )
            ctx.exit(2)


def reorient_sequence(blast_df, input, out_file, gene, i):
    # get the start
    dnaa_start_on_chromosome = blast_df["qstart"][i]
    strand = "forward"
    if blast_df["qstart"][i] > blast_df["qend"][i]:
        strand = "reverse"

    top_hit = blast_df["sseqid"][i]
    top_hit_length = blast_df["slen"][i]
    covered_len = blast_df["length"][i]
    coverage = round(covered_len / top_hit_length * 100, 2)
    ident = blast_df["nident"][i]
    identity = round(ident / covered_len * 100, 2)

    logger.info(
        f"{gene} gene identified. It starts at coordinate {dnaa_start_on_chromosome} on the {strand} strand in your input file."
    )
    logger.info(
        f"The best hit with a valid start codon in the database is {top_hit}, which has length of {top_hit_length} AAs."
    )
    logger.info(
        f"{covered_len} AAs were covered by the best hit, with an overall coverage of {coverage}%."
    )
    logger.info(f"{ident} AAs were identical, with an overall identity of {identity}%.")
    logger.info(f"Re-orienting.")

    ####################
    # reorientation
    ####################
    record = SeqIO.read(input, "fasta")
    # length of chromosome
    length = len(record.seq)

    # reorient to start at the terminase
    if strand == "forward":
        left = record.seq[(int(dnaa_start_on_chromosome) - 1) : length]
        right = record.seq[0 : int(dnaa_start_on_chromosome) - 1]
        total_seq = left + right

    # revese compliment if the strand is negative
    if strand == "reverse":
        record.seq = record.seq.reverse_complement()
        left = record.seq[(length - int(dnaa_start_on_chromosome)) : length]
        right = record.seq[0 : (length - int(dnaa_start_on_chromosome))]
        total_seq = left + right

    # updates the sequence
    record.seq = total_seq

    # writes to file
    with open(out_file, "w") as out_fa:
        SeqIO.write(record, out_fa, "fasta")


def reorient_sequence_random(input, out_file, start, strand):
    """
    for dnaapler random
    """

    ####################
    # reorientation
    ####################
    record = SeqIO.read(input, "fasta")
    # length of chromosome
    length = len(record.seq)

    # reorient to start at the terminase
    # forward is 1 from pyrodigal
    if strand == 1:
        left = record.seq[(int(start) - 1) : length]
        right = record.seq[0 : int(start) - 1]
        total_seq = left + right

    # revese compliment if the strand is -1 from pyrodigal
    if strand == -1:
        record.seq = record.seq.reverse_complement()
        left = record.seq[(length - int(start)) : length]
        right = record.seq[0 : (length - int(start))]
        total_seq = left + right

    # updates the sequence
    record.seq = total_seq

    # writes to file
    with open(out_file, "w") as out_fa:
        SeqIO.write(record, out_fa, "fasta")


# function to touch create a file
# https://stackoverflow.com/questions/12654772/create-empty-file-using-python
def touch_file(path):
    with open(path, "a"):
        os.utime(path, None)


# to create empty fasta file files
def touch_output_files(out_dir, prefix):
    touch_file(os.path.join(out_dir, prefix + "_reoriented.fasta"))
